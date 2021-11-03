import datetime
import logging
import time
from urllib import parse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from iotile_cloud.utils.gid import IOTileDeviceSlug, IOTileProjectSlug, IOTileStreamSlug, IOTileVariableSlug

from apps.physicaldevice.models import Device, DeviceStatus
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerInternalError
from apps.streamdata.helpers import StreamDataBuilderHelper
from apps.streamer.models import Streamer, StreamerReport
from apps.streamevent.helpers import EncodedStreamToEventDataHelper
from apps.streamfilter.cache_utils import cached_serialized_filter_for_slug
from apps.streamfilter.process import FilterHelper
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.data_helpers.manager import DataManager
from apps.utils.gid.convert import formatted_gdid, formatted_gsid, get_vid_from_gvid, int2did, int2vid
from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.timezone_utils import convert_to_utc, str_utc

from .process_report import ProcessReportV2Action

user_model = get_user_model()
logger = logging.getLogger(__name__)

_MAX_NUMBER_OF_RETRIES = 100


def get_chopped_report_retry_delay(attempt):
    # SQS has a maximum delay of 15min
    retry_base_delay = 15 * 60  # 15min
    return retry_base_delay


class HandleChoppedReportV2Action(ProcessReportV2Action):

    _all_stream_filters = {}
    _event_entries = []
    _data_timestamps = []
    _attempt_count = 0
    _ref_reboot = None

    @classmethod
    def _arguments_ok(self, args):
        """
        - 'attempt_count' : Should be less than _MAX_NUMBER_OF_RETRIES
        - 'rpt'           : Chopped Report ID
        """
        return Action._check_arguments(
            args=args, task_name='HandleChoppedReportV2Action',
            required=['attempt_count', 'rpt', ], optional=[]
        )

    def _initialize_from_device_streamer(self, parser):
        # Initialize all variables before reading report
        super(HandleChoppedReportV2Action, self)._initialize_from_device_streamer(parser)

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
        number_of_entries = len(self._data_entries)
        logger.info('Updating {} entries'.format(number_of_entries))
        for i in range(number_of_entries):
            item = self._data_entries[i]
            old_ts = self._data_timestamps[i]
            if item.timestamp != old_ts:
                DataManager.save('data', item, update_fields=['timestamp', 'status', 'dirty_ts'])
            else:
                logger.info('Skipping commit (no ts change): {}'.format(item))

        '''
        for item in self._data_entries:
            DataManager.save('data', item, update_fields=['timestamp', 'status', 'dirty_ts'])
        '''

    def _post_read_stream_data(self):
        """
        Do any post-processing:
        a) If combined report, do reboot fixups
        b) Check filters apply and if so, create a single filter per stream

        :return: Nothing
        """
        if self._count and (self._actual_first_id != None) and (self._actual_last_id != None):

            # Fixup any needed timestamps
            if self._ref_reboot:
                self._handle_reboots_if_needed(self._ref_reboot)

            # Because we have now fixed-up any reboots, it is safe to process filters here
            for stream in self._data_builder.get_cached_streams():
                if stream:
                    stream_slug = stream.slug
                    if stream_slug not in self._all_stream_filters:
                        # "expensive" call, call once for each stream in the report
                        self._all_stream_filters[stream_slug] = cached_serialized_filter_for_slug(stream_slug)

    def _process_fixup(self):

        # To prevent uncessary work, keep a copy of the old timestamps before they get updated
        # This will be used to determine if we need to commit any given data point
        # (We won't if the old and new timestamp is the same)
        self._data_timestamps = []

        # 1. Read existing data from DB
        qs = DataManager.filter_qs(
            'data',
            device_slug=self._device.slug,
            streamer_local_id__gte=self._actual_first_id,
            streamer_local_id__lte=self._actual_last_id
        ).order_by('streamer_local_id')
        logger.info('processing {} data entries'.format(qs.count()))
        for item in qs:
            self._data_entries.append(item)
            self._data_timestamps.append(item.timestamp)
            self._data_builder.check_if_stream_is_enabled(slug=item.stream_slug)
            self._count += 1
            if get_vid_from_gvid(item.variable_slug) == SYSTEM_VID['REBOOT']:
                self._reboot_ids.append(item.streamer_local_id)

        # 2. Do any post-processing on the array of data data_entries
        #    - Reboots
        #    - Filters
        self._post_read_stream_data()

        self._update_stream_data()

        # 3. If any stream is encoded, create stream events here
        # We are assuming devices with these functionality will also send user reports
        # with reboots merged, so we will need to be sure reboots get fixed on the data_entries
        # before we call this.
        # For now, don't worry about reboots
        self._process_encoded_stream_data()
        self._update_encoded_stream_data()

        # 4. We did not process filters for chopped devices, so need to do it now
        if self._count:
            filter_helper = FilterHelper()
            filter_helper.process_filter_report(self._data_entries, self._all_stream_filters)

    def process(self):

        assert self._streamer_report
        self._streamer = self._streamer_report.streamer
        assert self._streamer
        self._device = self._streamer.device
        assert self._device

        self._actual_first_id = self._streamer_report.actual_first_id
        self._actual_last_id = self._streamer_report.actual_last_id

        if self._actual_first_id == self._actual_last_id:
            logger.warning('Aborting because SEQID: {0} to {1}'.format(self._actual_first_id, self._actual_last_id))
            return

        logger.info('Reprocessing from SEQID {0} to {1}'.format(self._actual_first_id, self._actual_last_id))

        self._data_builder = StreamDataBuilderHelper()
        self._data_entries = []
        self._all_stream_filters = {}
        self._event_entries = []
        self._reboot_ids = []
        self._count = 0

        # 1. Check if we have the rest of the report we need on the database to process
        project_slug = IOTileProjectSlug(self._device.project.slug)
        reboot_variable = IOTileVariableSlug(SYSTEM_VID['REBOOT'], project=project_slug)
        complete_variable = IOTileVariableSlug(SYSTEM_VID['COMPLETE_REPORT'], project=project_slug)

        complete_slug = IOTileStreamSlug()
        complete_slug.from_parts(project=project_slug, device=self._device.slug, variable=complete_variable)

        reboot_stream_slug = IOTileStreamSlug()
        reboot_stream_slug.from_parts(project=project_slug, device=self._device.slug, variable=reboot_variable)

        logger.info('Looking for future reboots: {}'.format(reboot_stream_slug))
        q = Q(
            stream_slug=str(reboot_stream_slug),
            streamer_local_id__gt=self._actual_last_id,
        ) | Q(
            stream_slug=str(complete_slug),
            streamer_local_id__gt=self._actual_last_id,
            int_value=self._streamer.index
        )
        check_qs = DataManager.filter_qs_using_q('data', q, extras=['int_value']).order_by('streamer_local_id')

        if check_qs.count():
            ref = check_qs.first()
            logger.info('Found {}'.format(ref))
            if ref.variable_slug == str(reboot_variable):
                # Found reboot. Need to fix up data
                logger.info('Found with incremental_id={} at ts={}. Need to fix up data'.format(
                    ref.incremental_id, ref.timestamp
                ))
                self._ref_reboot = ref
                self._received_dt = ref.timestamp
                self._process_fixup()
            else:
                logger.info('No chopped report reprocessing is required')
        else:
            if self._attempt_count == _MAX_NUMBER_OF_RETRIES:
                logger.info('Too many attempts, giving up')
                self.notify_admins(
                    'HandleChoppedReportV2Action',
                    'Too many attempts waiting for continuation of rpt={}'.format(str(self._streamer_report.id))
                )
            else:
                logger.info('No additional chopped data. Rescheduling with attempt = {}'.format(self._attempt_count + 1))
                HandleChoppedReportV2Action.schedule(
                    delay_seconds=get_chopped_report_retry_delay(self._attempt_count),
                    args={
                        'rpt': str(self._streamer_report.id),
                        'attempt_count': self._attempt_count + 1
                    }
                )

    def execute(self, arguments):
        self.sqs_arguments = arguments
        if HandleChoppedReportV2Action._arguments_ok(arguments):

            rpt_id = arguments['rpt']
            self._attempt_count = arguments['attempt_count']

            try:
                self._streamer_report = StreamerReport.objects.get(id=rpt_id)
            except StreamerReport.DoesNotExist:
                raise WorkerActionHardError('Streamer Report not Found {}'.format(rpt_id))

            self.process()

    @classmethod
    def schedule(cls, args, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        """
        schedule function should always have at least args and queue_name as arguments
        :param args:
        :param queue_name:
        :param delay_seconds: optional
        :return:
        """
        module_name = cls.__module__
        class_name = cls.__name__
        logger.info('Using module_name={0}, class_name={1}'.format(module_name, class_name))
        if HandleChoppedReportV2Action._arguments_ok(args):
            Action._schedule(queue_name, module_name, class_name, args, delay_seconds)
