import datetime
import logging
import time
from urllib import parse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.dateparse import parse_datetime

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


class ReProcessDataV2Action(ProcessReportV2Action):
    _all_stream_filters = {}
    _event_entries = []

    def _initialize_from_device_streamer(self, parser):
        # Initialize all variables before reading report
        super(ReProcessDataV2Action, self)._initialize_from_device_streamer(parser)

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
        for item in self._data_entries:
            DataManager.save('data', item)

    def _post_read_stream_data(self):
        """
        Do any post-processing:
        a) If combined report, do reboot fixups
        b) Check filters apply and if so, create a single filter per stream

        :return: Nothing
        """
        if self._count and (self._actual_first_id != None) and (self._actual_last_id != None):

            # Fixup any needed timestamps
            self._handle_reboots_if_needed()

            # Because we have now fixed-up any reboots, it is safe to process filters here
            for stream in self._data_builder.get_cached_streams():
                if stream:
                    stream_slug = stream.slug
                    if stream_slug not in self._all_stream_filters:
                        # "expensive" call, call once for each stream in the report
                        self._all_stream_filters[stream_slug] = cached_serialized_filter_for_slug(stream_slug)

            filter_helper = FilterHelper()
            filter_helper.process_filter_report(self._data_entries, self._all_stream_filters)

    def process(self):
        start_time = time.time()

        assert self._streamer_report
        self._streamer = self._streamer_report.streamer
        assert self._streamer
        self._device = self._streamer.device
        assert self._device

        self._data_builder = StreamDataBuilderHelper()
        self._data_entries = []
        self._all_stream_filters = {}
        self._event_entries = []
        self._reboot_ids = []
        self._count = 0

        self._received_dt = self._streamer_report.sent_timestamp

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

        return self._count

    def execute(self, arguments):
        self.sqs_arguments = arguments
        if 'rpt' in arguments and 'start' in arguments and 'end' in arguments:

            rpt_id = arguments['rpt']
            self._actual_first_id = int(arguments['start'])
            self._actual_last_id = int(arguments['end'])

            try:
                self._streamer_report = StreamerReport.objects.get(id=rpt_id)
                self.process()
            except StreamerReport.DoesNotExist:
                raise WorkerActionHardError('Streamer Report not Found {}'.format(rpt_id))
        else:
            raise WorkerActionHardError('RPT/Start/End arguments. Arguments: {}'.format(arguments))

    @classmethod
    def schedule(cls, args, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        """
        schedule function should always have at least args and queue_name as arguments
        :param args:
        :param queue_name:
        :param delay_seconds: optional
        :return:
        """

        if 'rpt' in args and 'start' in args and 'end' in args:
            module_name = cls.__module__
            class_name = cls.__name__
            logger.info('Using module_name={0}, class_name={1}'.format(module_name, class_name))

            Action._schedule(queue_name, module_name, class_name, args, delay_seconds)
        else:
            raise WorkerActionHardError('Missing fields in argument payload.\nReceived args: {}\nRequired args : bucket, key'.format(args))
