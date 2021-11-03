import datetime
import logging
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q

from apps.physicaldevice.models import Device
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError
from apps.streamdata.helpers import StreamDataBuilderHelper
from apps.utils.data_helpers.manager import DataManager
from apps.utils.gid.convert import get_vid_from_gvid
from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.timezone_utils import convert_to_utc

from .process_report import ProcessReportV2Action

user_model = get_user_model()
logger = logging.getLogger(__name__)


class ReProcessOneRebootV2Action(ProcessReportV2Action):
    """
    This task can be used to move a whole block of data to a different timestamp.
    The block is defined from the "reboot_id" to either the next reboot, or none exist,
    the end of the data.
    The "ref_id" is a data record with a good timestamp. This reference will be used to
    compute the base timestamp, and all data will be based on it.
    If the reference is before the reboot, then all data is moved to the right, with
    an optional "offset" to be used to separate the data from the left side.
    If the reference is on the right, then all data will be moved to the left of the reference.
    """
    _all_stream_filters = {}
    _event_entries = []

    @classmethod
    def _arguments_ok(self, args):
        """
        The "reboot_id" represents the left most part of the block we will process
        The "ref_id" can be on the left or right of the reboot_id. If on the right, this is usually the next reboot
         plus one, but can be any reference in the future that has a correct timestamp.
         If the ref is on the left, then an optional "offset" is used to add to the base timestamp.
        """
        return Action._check_arguments(
            args=args, task_name='ReProcessOneRebootV2Action',
            required=['reboot_id', 'ref_id', 'device_slug', ], optional=['offset', ]
        )

    def _get_data_entries(self, reboot_data):
        """
        First, get all reboots ahead of the reboot_id passed to the task.
        If reboots found, then find all data within the reboot and the next one.
        If no reboots found, then just find all data from the reboot to the end.
        :param reboot_data: reboot data for the reboot id passed to task.
        :return: DataStream filter from the reboot to the next reboot or end of data
        """
        qs = DataManager.filter_qs(
            'data',
            stream_slug=reboot_data.stream_slug,
            streamer_local_id__gt=reboot_data.streamer_local_id
        ).order_by('streamer_local_id')

        if qs.count() == 0:
            q = Q(device_slug=self._device.slug,
                  streamer_local_id__gte=reboot_data.streamer_local_id)
        else:
            next_reboot = qs.first()
            q = Q(device_slug=self._device.slug,
                  streamer_local_id__gte=reboot_data.streamer_local_id,
                  streamer_local_id__lt=next_reboot.streamer_local_id)

        self._reboot_ids.append(reboot_data.streamer_local_id)
        qs = DataManager.filter_qs_using_q('data', q).order_by('streamer_local_id')
        logger.info('processing {} data entries'.format(qs.count()))
        for item in qs:
            self._data_entries.append(item)
            self._data_builder.add_stream_to_cache(key=item.stream_slug)
            self._count += 1

    def _update_encoded_stream_data(self):
        first_id = None
        last_id = None
        for event in self._event_entries:
            if not first_id:
                first_id = event.streamer_local_id
            last_id = event.streamer_local_id

        if len(self._event_entries) and first_id and last_id:
            # Delete any previous records
            qs = DataManager.filter_qs(
                'event',
                device_slug=self._device.slug,
                streamer_local_id__gte=first_id,
                streamer_local_id__lte=last_id
            )
            logger.info('Deleting {} StreamEvents'.format(qs.count()))
            qs.delete()

            logger.info('Recreating {} StreamEvents'.format(len(self._event_entries)))
            DataManager.bulk_create('event', self._event_entries)

    def _update_stream_data(self):
        logger.info('Updating {} entries'.format(len(self._data_entries)))
        with transaction.atomic():
            for item in self._data_entries:
                DataManager.save('data', item)

    def _move_reboot_based_on_ref(self, reboot_data, reference_data, offset):
        """
        If the reference is before the reboot, then all data is moved to the right, with
        an optional "offset" to be used to separate the data from the left side.
        If the reference is on the right, then all data will be moved to the left of the reference.
        """

        if reference_data.streamer_local_id > reboot_data.streamer_local_id:
            base_ts = reference_data.timestamp - datetime.timedelta(seconds=reboot_data.device_timestamp)
            logger.info('ref_data={0}, base_ts={1}'.format(reference_data.timestamp, base_ts))
        else:
            base_ts = reference_data.timestamp + datetime.timedelta(seconds=offset)
            logger.info('ref_data={0}, base_ts={1}'.format(reference_data.timestamp, base_ts))

        for item in self._data_entries:
            if get_vid_from_gvid(item.variable_slug) in [SYSTEM_VID['TRIP_START'], SYSTEM_VID['TRIP_END']]:
                continue
            item.timestamp = convert_to_utc(base_ts + datetime.timedelta(seconds=item.device_timestamp))
            item.status = 'cln'
            item.dirty_ts = False

    def process_reboot(self, reboot_data, reference_data, offset):
        start_time = time.time()

        try:
            Device.objects.get(slug=reboot_data.device_slug)
        except Device.DoesNotExist:
            raise WorkerActionHardError('Device not Found {}'.format(reboot_data.device_slug))

        self._data_builder = StreamDataBuilderHelper()
        self._data_entries = []
        self._all_stream_filters = {}
        self._event_entries = []
        self._reboot_ids = []
        self._count = 0

        # 1. Find next reboot, if any and use to collect all entries
        #    to be processed
        self._get_data_entries(reboot_data)

        # 2. Check if we should move to the left or right
        self._move_reboot_based_on_ref(reboot_data, reference_data, offset)

        self._update_stream_data()

        # 3. If any stream is encoded, create stream events here
        # We are assuming devices with these functionality will also send user reports
        # with reboots merged, so we will need to be sure reboots get fixed on the data_entries
        # before we call this.
        # For now, don't worry about reboots
        self._process_encoded_stream_data()
        self._update_encoded_stream_data()

        logger.info('Time to process {0} reboot {1}: {2} sec'.format(self._count,
                                                                     reboot_data.stream_slug,
                                                                     time.time() - start_time))

        return self._count

    def execute(self, arguments):
        self.sqs_arguments = arguments
        if ReProcessOneRebootV2Action._arguments_ok(arguments):

            device_slug = arguments['device_slug']
            reboot_id = int(arguments['reboot_id'])
            reference_id = int(arguments['ref_id'])
            offset = int(arguments['offset']) if 'offset' in arguments else 1

            try:
                self._device = Device.objects.get(slug=device_slug)
            except Device.DoesNotExist:
                raise WorkerActionHardError('Device not Found {}'.format(device_slug))

            try:
                reboot_data = DataManager.get('data', streamer_local_id=reboot_id, device_slug=device_slug)
            except ObjectDoesNotExist:
                raise WorkerActionHardError('Reboot not Found {}'.format(reboot_id))

            try:
                reference_data = DataManager.get('data', streamer_local_id=reference_id, device_slug=device_slug)
            except ObjectDoesNotExist:
                raise WorkerActionHardError('Reference not Found {}'.format(reference_id))

            self.process_reboot(reboot_data, reference_data, offset)

    @classmethod
    def schedule(cls, args=None, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        module_name = cls.__module__
        class_name = cls.__name__
        if ReProcessOneRebootV2Action._arguments_ok(args):
            Action._schedule(queue_name, module_name, class_name, args, delay_seconds)
