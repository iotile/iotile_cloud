import datetime
import logging
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.ota.utils.streamer import DeploymentActionStreamerHelper
from apps.physicaldevice.models import DeviceStatus
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerInternalError
from apps.streamer.report.parser import ReportParser
from apps.streamevent.helpers import EncodedStreamToEventDataHelper
from apps.streamfilter.cache_utils import cached_serialized_filter_for_slug
from apps.streamfilter.process import FilterHelper
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.data_helpers.manager import DataManager
from apps.utils.gid.convert import get_vid_from_gvid
from apps.utils.iotile.streamer import STREAMER_SELECTOR
from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.timezone_utils import convert_to_utc

from ..common.base_action import ProcessReportBaseAction, get_utc_read_data_timestamp
from ..misc.forward_streamer_report import ForwardStreamerReportAction

user_model = get_user_model()
logger = logging.getLogger(__name__)
DELAY_SECONDS = 60 * 5  # in seconds


class ProcessReportV2Action(ProcessReportBaseAction):
    _all_stream_filters = {}
    _event_entries = []

    def _preprocess_parsed_report(self, parser):
        # Initialize all variables before reading report
        self._initialize()
        self._initialize_from_device_streamer(parser)
        self._all_stream_filters = {}
        self._event_entries = []

    def _remove_reboots_from_data_entries(self):
        new_data = []
        for item in self._data_entries:
            if get_vid_from_gvid(item.variable_slug) != SYSTEM_VID['REBOOT']:
                new_data.append(item)
        self._data_entries = new_data

    def _handle_trip_system_data(self):
        """

        Special handling of TRIP variables due to a FW limitation
        that does not allow POD-1M's streamer 2 to include reboots.
        For TRIP_START and TRIP_END, the mobile phone adds the epoch
        time as value. We can therefore use this as a base timestamp.
        For TRIP_RECORD, use the TRIP_START as base_ts, but note that
        because we have no reboots, we cannot really fix any post-reboot
        items. For that case, just try to guess based on device_timestamp
        being smaller than a previous item
        """
        base_ts = None
        base_device_timestamp = 0
        for i in range(len(self._data_entries)):
            item = self._data_entries[i]
            if get_vid_from_gvid(item.variable_slug) == SYSTEM_VID['TRIP_START']:
                item.timestamp = datetime.datetime.fromtimestamp(item.int_value, datetime.timezone.utc)
                base_ts = item.timestamp - datetime.timedelta(seconds=item.device_timestamp)
                item.status = 'utc'
            elif get_vid_from_gvid(item.variable_slug) == SYSTEM_VID['TRIP_END']:
                item.timestamp = datetime.datetime.fromtimestamp(item.int_value, datetime.timezone.utc)
                item.status = 'utc'
            elif base_ts and not item.has_utc_synchronized_device_timestamp:
                # (This fix should only be done if device_timestamp is not UTC)
                # Since the base_ts from the TRIP_START is very reliable, fix up all timestamps
                # Unfortunately, as of writing, the Start/End come on a different streamer, so
                # this won't really be enough to fix all the data
                if i and item.device_timestamp < self._data_entries[i - 1].device_timestamp:
                    base_device_timestamp += self._data_entries[i - 1].device_timestamp
                device_timestamp = item.device_timestamp + base_device_timestamp
                item.timestamp = convert_to_utc(base_ts + datetime.timedelta(seconds=device_timestamp))

    def _handle_reboots_if_needed(self, reference_reboot=None):
        contains_trip_system_data = False
        end_of_block_dt = self._received_dt
        if reference_reboot:
            # Use this method for handling chopped reports
            # In this case, the reference is the first reboot after the chopped report
            last = self._data_entries[-1]
            base_ts = reference_reboot.timestamp - datetime.timedelta(seconds=last.device_timestamp)
            logger.info('_received_dt={0}, ref_reboot={1}, base_ts={2}'.format(
                self._received_dt, reference_reboot.timestamp, base_ts
            ))
        else:
            base_ts = self._received_dt - datetime.timedelta(seconds=self._streamer_report.device_sent_timestamp)
            logger.info('_received_dt={0}, device_sent_ts={1}, base_ts={2}'.format(
                self._received_dt, self._streamer_report.device_sent_timestamp, base_ts
            ))
        no_reboots_found = True
        for i in reversed(range(len(self._data_entries))):
            item = self._data_entries[i]
            # If timestamp was already based on UTC (with the device RTC)
            # then do not process reboot
            if item.has_utc_synchronized_device_timestamp:
                item.status = 'utc'
                item.dirty_ts = False
                if item.timestamp is None:
                    # If timestamp is not set, set it here
                    item.timestamp = get_utc_read_data_timestamp(base_ts, item.device_timestamp)
                continue
            # Do not fix TRIP START/END records. We will special handle them below
            if get_vid_from_gvid(item.variable_slug) in [SYSTEM_VID['TRIP_START'], SYSTEM_VID['TRIP_END']]:
                # Need to handle trip system data
                contains_trip_system_data = True
                continue

            if not base_ts:
                base_ts = end_of_block_dt - datetime.timedelta(seconds=item.device_timestamp)
                logger.info("Base ts at the end of block {}".format(base_ts))

            item.timestamp = convert_to_utc(base_ts + datetime.timedelta(seconds=item.device_timestamp))
            item.status = 'cln' if no_reboots_found else 'drt'
            item.dirty_ts = (item.status == 'drt')
            if get_vid_from_gvid(item.variable_slug) == SYSTEM_VID['REBOOT']:
                if no_reboots_found:
                    no_reboots_found = False
                logger.info('Base ts resetted to None after reboot={}'.format(item.incremental_id))
                # Because we don't know any better at this poing, simple assume the begining of
                # this block is the end of the next block (remember, we are going backwards)
                end_of_block_dt = base_ts - datetime.timedelta(seconds=1)
                logger.info('end_of_block_dt={0}, base_ts={1}'.format(end_of_block_dt, base_ts))
                base_ts = None

        if contains_trip_system_data:
            self._handle_trip_system_data()

        # Now clean the data on the left most side, which should be adjusted to the last entry we have and set
        # to clean. Only do this if we left if drt on the lagorithm above
        if self._data_entries[0].status == 'drt':
            logger.info('Cleaning up left most block')
            # Get the base_ts of the previous report and use that
            reports = self._streamer.reports.filter(incremental_id__lt=self._streamer_report.incremental_id, actual_last_id__gt=0)
            if reports:
                last_report = reports.order_by('incremental_id').last()
                if last_report:
                    base_ts = last_report.sent_timestamp - datetime.timedelta(seconds=last_report.device_sent_timestamp)
                    for i in range(len(self._data_entries)):
                        item = self._data_entries[i]
                        assert item.streamer_local_id > last_report.actual_last_id
                        if get_vid_from_gvid(item.variable_slug) == SYSTEM_VID['REBOOT']:
                            break
                        item.timestamp = convert_to_utc(base_ts + datetime.timedelta(seconds=item.device_timestamp))
                        item.status = 'cln'
                        item.dirty_ts = False
                else:
                    raise WorkerInternalError('Was not able to fetch last streamer report')
            else:
                # If the device got just claimed, it may not have any previous reports.
                # In that case, the left most block will stay based on the most right block
                # and it remains dirty (as we don't have any extra info from the past)
                logger.info('No previous streamer report. Skipping post-processing of left most block')
        else:
            logger.info('No left block to cleanup')

    def _syncup_e2_data(self):
        """
        For every stream of type E2 (Unstructured Events with Data Pointer),
        Find all associated events, and for each, update its timestamp
        """
        for stream in self._data_builder.get_cached_streams():
            if stream and stream.enabled and stream.data_type == 'E2':
                seq_ids = []
                data_map = {}
                for stream_data in self._data_entries:
                    # If the data point has RTC synchronized timing, ignore
                    if not stream_data.has_utc_synchronized_device_timestamp:
                        if stream_data.stream_slug == stream.slug:
                            seq_id = stream_data.int_value
                            seq_ids.append(seq_id)
                            data_map[seq_id] = stream_data
                if seq_ids:
                    event_qs = DataManager.filter_qs('event', streamer_local_id__in=seq_ids, stream_slug=stream.slug)
                    # Django’s default behavior is to run in autocommit mode
                    # An atomic transaction reduces this overhead
                    unprocessed_seq_ids = []
                    with transaction.atomic():
                        for event in event_qs:
                            data_item = data_map.pop(event.incremental_id, None)
                            if data_item:
                                logger.info('Updating event {} with timestamp from data {}'.format(
                                    event.id, data_item.id
                                ))
                                event.timestamp = data_item.timestamp
                                event.device_timestamp = data_item.device_timestamp
                                DataManager.save('event', event)
                            else:
                                logger.warning(
                                    'Found event without a data pointer: {}:{}'.format(
                                        event.stream_slug, event.incremental_id
                                    )
                                )
                                unprocessed_seq_ids.append(event.incremental_id)

                    if unprocessed_seq_ids:
                        sns_staff_notification('The following events for {} had no data pointer: {}'.format(
                            stream.slug, str(unprocessed_seq_ids)
                        ))

    def _process_encoded_stream_data(self):
        """
        If any stream is encoded, process all data_entries and create the required
        stream events from the encoded stream data.

        :return: Nothing
        """
        msgs = []
        for stream in self._data_builder.get_cached_streams():
            if stream and stream.enabled and stream.is_encoded:
                encoded_event_helper = EncodedStreamToEventDataHelper(stream)
                for stream_data in self._data_entries:
                    # The following function will create stream events when appropriate
                    event = encoded_event_helper.process_data_point(stream_data)
                    if event:
                        self._event_entries.append(event)

                if encoded_event_helper.error_count:
                    if self._streamer and self._streamer_report:
                        msg = 'Streamer {0} (RPT {1}) error: {2}'.format(
                            self._streamer.slug,
                            self._streamer_report.incremental_id,
                            encoded_event_helper.error_count
                        )
                    else:
                        msg = 'Stream {0} error: {1}'.format(
                            stream.slug,
                            encoded_event_helper.error_count
                        )
                    msg += ' encoded packets were not processed due to errors'
                    msgs.append(msg)

        if msgs:
            for msg in msgs:
                logger.warning(msg)
            # TODO: Rollback when packed data is robust. For now, send SNS only
            # raise WorkerActionHardError(msgs[-1])
            if len(msgs) > 10:
                msgs = msgs[0:9]
            sns_staff_notification('/n'.join(msgs))

    def _process_ota_data(self):
        """
        If the device was updated, one or both of the following streams will be send
        by the device:
        - OS_TAG_VERSION: New OS Tag and version. 20 bit number that indicates the
          combination of tiles that the device is running
        - APP_TAG_VERSION: New App (SG) Tag and version. 20 bit number that
          indicates the sensor graph that the device is running.

        In both cases, the value also includes 12 additional bits for the version
        in the form of 6.6.

        The full value encoding is:
        - 20bit: TAG
        - 6bit: Major
        - 6bit: Minor

        :return: Nothing
        """
        os_tag_vid = SYSTEM_VID['OS_TAG_VERSION']
        app_tag_vid = SYSTEM_VID['APP_TAG_VERSION']

        for data in self._data_entries:
            vid = get_vid_from_gvid(data.variable_slug)
            if vid in [os_tag_vid, app_tag_vid]:
                # Use helper to decode data value and update all required records
                helper = DeploymentActionStreamerHelper(self._device)
                helper.complete_action(vid, data)

    def _commit_stream_event_data(self):
        if self._event_entries:
            DataManager.bulk_create('event', self._event_entries)

    def _post_read_stream_data(self):
        """
        Do any post-processing:
        a) Handle any reboots
        b) Remove reboots from non-system reports (to avoid duplicates)
        c) Process filters

        :return: Nothing
        """
        if self._count and (self._actual_first_id is not None) and (self._actual_last_id is not None):

            # Fixup any needed timestamps
            self._handle_reboots_if_needed()

            # Because reboots exist on all streams, we need to remove them from user streams
            # to ensure we don't get duplicates
            if self._streamer.selector != STREAMER_SELECTOR['SYSTEM']:
                self._remove_reboots_from_data_entries()

            # Process any OTA data
            self._process_ota_data()

            # Because we have now fixed-up any reboots, it is safe to process filters here
            for stream in self._data_builder.get_cached_streams():
                if stream:
                    stream_slug = stream.slug
                    if stream_slug not in self._all_stream_filters:
                        # "expensive" call, call once for each stream in the report
                        self._all_stream_filters[stream_slug] = cached_serialized_filter_for_slug(stream_slug)
        else:
            logger.info('Skipping post-processing: count={0}, _actual_first_id={1}, _actual_last_id={2}'.format(
                self._count, self._actual_first_id, self._actual_last_id
            ))

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

            device_status = DeviceStatus.get_or_create(self._device)

            with transaction.atomic():
                self._streamer_report.actual_first_id = self._actual_first_id
                self._streamer_report.actual_last_id = self._actual_last_id
                self._streamer_report.save()
                self._streamer.last_id = self._streamer_report.actual_last_id
                self._streamer.last_reboot_ts = base_dt_utc
                self._streamer.save()
                # Update Device Status for Hearthbeat notifications
                if self._streamer_report.actual_last_id > device_status.last_known_id:
                    device_status.last_known_id = self._streamer_report.actual_last_id
                    device_status.save()

        elif self._streamer_report.actual_first_id is None and self._streamer_report.actual_last_id is None:
            self._streamer_report.actual_first_id = 0
            self._streamer_report.actual_last_id = 0
            self._streamer_report.save()

    def _scheduled_chopped_report_fixup(self):
        logger.info('No more data yet. Rescheduling with attempt = {}'.format(1))
        args = {
            'rpt': str(self._streamer_report.id),
            'attempt_count': 1
        }
        delay_seconds = 900
        module_name = 'apps.streamer.worker.v2_bin.handle_chopped_report'
        class_name = 'HandleChoppedReportV2Action'
        logger.info('Using module_name={0}, class_name={1}'.format(module_name, class_name))

        logger.info('Scheduling new HandleChoppedReportV2Action with delay={}s'.format(delay_seconds))
        Action._schedule(getattr(settings, 'SQS_WORKER_QUEUE_NAME'), module_name, class_name, args, delay_seconds)

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

        # 1.5. Ensure this is not a V/V1 selector
        if parser.header['streamer_selector'] == STREAMER_SELECTOR['USER_NO_REBOOTS']:
            logger.error('Incorrect Selector: {}'.format(hex(STREAMER_SELECTOR['USER_NO_REBOOTS'])))
            raise WorkerActionHardError('Unexpected selector for V2 engine: {}'.format(hex(STREAMER_SELECTOR['USER_NO_REBOOTS'])))

        # 2. Do any post-processing on the array of data data_entries
        self._post_read_stream_data()

        # 3. Commit all stream data data_entries
        self._commit_stream_data(parser=parser)

        # 4. If any stream is encoded, create stream events here
        # We are assuming devices with these functionality will also send user reports
        # with reboots merged, so we will need to be sure reboots get fixed on the data_entries
        # before we call this.
        # For now, don't worry about reboots
        self._process_encoded_stream_data()
        self._commit_stream_event_data()

        # 5. Update all associated records (e.g. streamer and streamer report)
        self._update_streamer_and_streamer_report(parser=parser, base_dt_utc=base_dt_utc)

        if self._count:
            if self._chopped_report:
                self._scheduled_chopped_report_fixup()
            else:
                # 6. Schedule any additional tasks
                filter_helper = FilterHelper()
                filter_helper.process_filter_report(self._data_entries, self._all_stream_filters, user_slug=self._user.slug)

                # 7. For any stream.data_type == E2, update the associated StreamEvent records ts
                self._syncup_e2_data()

            # Finally, forward the streamer report to any ArchFx Cloud (if enabled)
            ForwardStreamerReportAction.schedule(args={
                'org': self._device.org.slug,
                'report': str(self._streamer_report.id),
                'ext': '.bin'
            })

        logger.info('Time to process {0} report {1}: {2} sec'.format(
            self._count, self._streamer.slug, time.time() - start_time
        ))
        return self._count
