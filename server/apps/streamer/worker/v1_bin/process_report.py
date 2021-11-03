import datetime
import logging
import time
from urllib import parse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.physicaldevice.models import Device, DeviceStatus
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerInternalError
from apps.streamer.models import Streamer, StreamerReport
from apps.streamer.report.parser import ReportParser
from apps.streamfilter.cache_utils import cached_serialized_filter_for_slug
from apps.streamfilter.process import FilterHelper
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.gid.convert import formatted_gdid, formatted_gsid, get_vid_from_gvid, int2did, int2vid
from apps.utils.iotile.streamer import STREAMER_SELECTOR
from apps.utils.timezone_utils import convert_to_utc, str_utc

from ..common.base_action import ProcessReportBaseAction
from .handle_delay import HandleDelayAction
from .handle_reboot import HandleRebootAction

user_model = get_user_model()
logger = logging.getLogger(__name__)
DELAY_SECONDS = 60 * 5  # in seconds


class ProcessReportV1Action(ProcessReportBaseAction):
    _last_user_incremental_id = None
    _last_system_incremental_id = None
    _all_stream_filters = {}

    def _preprocess_parsed_report(self, parser):
        # Initialize all variables before reading report
        self._initialize()
        self._initialize_from_device_streamer(parser)

        self._last_user_incremental_id = None
        self._last_system_incremental_id = None
        self._all_stream_filters = {}

    def _handle_reboot(self, parser):
        logger.info('Reboot detected during processing. Scheduling handle reboot action...')
        logger.info("Reboot ids: {}".format(self._reboot_ids))
        reboot_args = {
            'device_slug': self._device.slug,
            'project_id': str(self._device.project.id),
            'block_end_id': parser.header['rpt_id'],  # end of block
            'block_start_id': self._device.last_known_id,  # start of block
            'reboot_ids': self._reboot_ids
        }
        HandleRebootAction.schedule(args=reboot_args, delay_seconds=DELAY_SECONDS)

    def _handle_delay_report(self):
        delay_args = {
            'device_slug': self._device.slug,
            'project_id': str(self._device.project.id),
            'start_id': self._streamer_report.actual_first_id,
            'end_id': self._streamer_report.actual_last_id,
            'report_id': str(self._streamer_report.id)
        }
        HandleDelayAction.schedule(args=delay_args, delay_seconds=DELAY_SECONDS)

    def _update_incremental_id_stats(self, item, incremental_id):
        """
        Keep track of the first and last incremental_id we see.
        Also keep track of this for both user and system reports.

        :param item: Report reading item
        :param incremental_id: Current incremental id
        :return: Nothing. Setting class local variables
        """
        super(ProcessReportV1Action, self)._update_incremental_id_stats(item, incremental_id)
        if bool(item['stream'] & (1 << 11)):
            self._last_system_incremental_id = incremental_id
        else:
            self._last_user_incremental_id = incremental_id

    def _post_read_stream_data(self):
        """
        Do any post-processing:
        a) Check filters apply and if so, create a single filter per stream

        :return: Nothing
        """
        if self._count and (self._actual_first_id != None) and (self._actual_last_id != None):
            for stream in self._data_builder.get_cached_streams():
                if stream:
                    stream_slug = stream.slug
                    if stream_slug not in self._all_stream_filters:
                        # "expensive" call, call once for each stream in the report
                        self._all_stream_filters[stream_slug] = cached_serialized_filter_for_slug(stream_slug)

    def _update_streamer_and_streamer_report(self, parser, base_dt_utc):
        """
        Update all records associated with this report with final updates
        a) Streamer with last_id
        b) StreamerReport with actual first/last IDs
        c) DeviceStatus record with heartbeat info

        :return: Nothing
        """

        if self._count:
            logger.info('Updating last_known_id: {} -> {}'.format(self._device.last_known_id, parser.header['rpt_id']))

            status = DeviceStatus.get_or_create(self._device)

            with transaction.atomic():
                self._streamer_report.actual_first_id = self._actual_first_id
                self._streamer_report.actual_last_id = self._actual_last_id
                self._streamer_report.save()
                self._streamer.last_id = self._streamer_report.actual_last_id
                self._streamer.last_reboot_ts = base_dt_utc
                self._streamer.save()
                # Update Device Status for Hearthbeat notifications
                if self._streamer_report.actual_last_id > status.last_known_id:
                    status.last_known_id = self._streamer_report.actual_last_id
                    status.save()

        elif self._streamer_report.actual_first_id == None and self._streamer_report.actual_last_id == None:
            self._streamer_report.actual_first_id = 0
            self._streamer_report.actual_last_id = 0
            self._streamer_report.save()

    def _schedule_additional_tasks(self, parser):
        """
        Process or schedule any additional tasks, like fixing reboots, update data status, etc.

        :return: Nothing
        """
        if self._count:
            if self._streamer.is_system:
                logger.info('Post processing for system report.')
                if len(self._reboot_ids) > 0:
                    self._handle_reboot(parser)
            else:
                lastest_reboot = self._get_last_reboot_data_point()
                if lastest_reboot and lastest_reboot.streamer_local_id:
                    if self._actual_first_id < lastest_reboot.streamer_local_id:
                        logger.info("Delayed report detected, scheduling HandleDelayAction...")
                        self._handle_delay_report()

            if self._streamer.is_system:
                self._device.last_known_id = parser.header['rpt_id']
                self._device.save()

    def process(self):
        start_time = time.time()

        parser = ReportParser()
        self._preprocess_parsed_report(parser)

        sent_timestamp = parser.header['sent_timestamp']
        assert (isinstance(sent_timestamp, int) and sent_timestamp >= 0)
        base_dt = self._received_dt - datetime.timedelta(seconds=sent_timestamp)
        base_dt_utc = convert_to_utc(base_dt)

        # 1. Parse readings from report
        self._read_stream_data(base_dt=base_dt, parser=parser)

        # 1.5. Ensure this is not a V2 selector
        if parser.header['streamer_selector'] == STREAMER_SELECTOR['USER']:
            raise WorkerActionHardError('Unexpected selector for V1 engine: {}'.format(STREAMER_SELECTOR['USER']))

        # 2. Do any post-processing on the array of data data_entries
        self._post_read_stream_data()

        # 3. Commit all stream data data_entries
        self._commit_stream_data(parser=parser)

        # 5. Update all associated records (e.g. streamer and streamer report)
        self._update_streamer_and_streamer_report(parser=parser, base_dt_utc=base_dt_utc)

        # 6. Schedule any additional tasks (e.g. update status, fix reboots, etc.)
        if self._count:
            self._schedule_additional_tasks(parser=parser)

            # Process filters here, but this is actually wrong as we are processing before
            # fixing any reboots TODO: Fix this
            filter_helper = FilterHelper()
            filter_helper.process_filter_report(self._data_entries, self._all_stream_filters)

        logger.info('Time to process {0} report {1}: {2} sec'.format(self._count, self._streamer.slug, time.time() - start_time))
        return self._count
