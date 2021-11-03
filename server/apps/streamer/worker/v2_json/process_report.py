import datetime
import logging
import os
import time

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.dateparse import parse_datetime
from iotile_cloud.utils.gid import IOTileStreamSlug, IOTileVariableSlug
from rest_framework.parsers import JSONParser

from apps.physicaldevice.models import DeviceStatus
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerInternalError

from apps.streamer.msg_pack import Python2CompatMessagePackParser
from apps.streamer.serializers import StreamerReportJsonPostSerializer
from apps.streamevent.helpers import StreamEventDataBuilderHelper
from apps.streamdata.helpers import StreamDataBuilderHelper
from apps.utils.data_helpers.manager import DataManager
from apps.utils.timezone_utils import convert_to_utc, formatted_ts, force_to_utc

from ..common.base_action import ProcessReportBaseAction
from ..misc.forward_streamer_report import ForwardStreamerReportAction
from .syncup_e2_data import SyncUpE2DataAction

user_model = get_user_model()
logger = logging.getLogger(__name__)


class ProcessReportV2JsonAction(ProcessReportBaseAction):
    _all_stream_filters = {}
    _event_entries = []
    _data_entries = []
    _deserialized_data = {}
    _actual_first_id = None
    _actual_last_id = None
    _event_build_helper = None
    _data_build_helper = None

    def _update_incremental_id_stats(self, item, incremental_id):
        """
        Keep track of the first and last incremental_id we see.
        We overwrite the base version because we need to handle
        the fact that we have two different arrays (data and event)
        and we need to make sure we end up with the earliest actual
        and latest last

        :param item: Report reading item
        :param incremental_id: Current incremental id
        :return: Nothing. Setting class local variables
        """
        if self._actual_first_id is None or incremental_id < self._actual_first_id:
            self._actual_first_id = incremental_id

        if self._actual_last_id is None or incremental_id > self._actual_last_id:
            self._actual_last_id = incremental_id

    def _process_event_data(self):
        """
        For every event in the report file, check if the incremental ID is larger than the
        last known id. If so, add to the commit list.
        Based on this, keep track of the actual first/last IDs
        """
        if 'events' not in self._deserialized_data:
            return

        original_first_id = self._deserialized_data['lowest_id']
        original_last_id = self._deserialized_data['highest_id']

        assert self._streamer

        stream_slug = IOTileStreamSlug()
        device_slug = self._device.slug
        project_slug = self._device.project.slug

        for item in self._deserialized_data['events']:
            incremental_id = item['streamer_local_id']
            assert (incremental_id >= original_first_id or incremental_id <= original_last_id)
            assert(incremental_id is not None and isinstance(incremental_id, int))

            if incremental_id > self._streamer.last_id:
                lid = item.pop('stream')
                # lid can either be a HEX string (`5020`) or an integer (`20512`)
                variable_slug = IOTileVariableSlug(lid, project=project_slug)
                stream_slug.from_parts(
                    project=project_slug,
                    device=device_slug,
                    variable=variable_slug
                )
                item['stream_slug'] = str(stream_slug)

                # Coretools is also formatting the timestamp without
                # a `Z` so we need to adjust the timestamp as well
                if 'timestamp' in item and item['timestamp'] is not None:
                    item['timestamp'] = force_to_utc(item['timestamp'])

                event = self._event_build_helper.process_serializer_data(item)
                # event can be None if stream is disabled
                if event is not None:
                    # For now, only handle UTC timestamps
                    if event.has_utc_synchronized_device_timestamp:
                        event.sync_utc_timestamp_from_device()
                    self._event_entries.append(event)
                    self._count += 1
            else:
                logger.info('Ignoring Streamer Report (older data)')

            # Keep track of the actual start/end incremental IDs
            self._update_incremental_id_stats(item, incremental_id)

    def _process_data(self):
        """
        For every data point in the report file, check if the incremental ID is larger than the
        last known id. If so, add to the commit list.
        Based on this, keep track of the actual first/last IDs
        """
        if 'data' not in self._deserialized_data:
            return

        original_first_id = self._deserialized_data['lowest_id']
        original_last_id = self._deserialized_data['highest_id']

        assert self._streamer

        stream_slug = IOTileStreamSlug()
        device_slug = self._device.slug
        project_slug = self._device.project.slug

        for item in self._deserialized_data['data']:
            incremental_id = item['streamer_local_id']
            assert (incremental_id >= original_first_id or incremental_id <= original_last_id)
            assert(incremental_id is not None and isinstance(incremental_id, int))

            if incremental_id > self._streamer.last_id:
                lid = item.pop('stream')
                # lid can either be a HEX string (`5020`) or an integer (`20512`)
                variable_slug = IOTileVariableSlug(lid, project=project_slug)
                stream_slug.from_parts(
                    project=project_slug,
                    device=device_slug,
                    variable=variable_slug
                )
                item['stream_slug'] = str(stream_slug)

                # Coretools will serialize its value as item.value
                # but on IOTile Cloud, this value really represents
                # item.int_value which will then use MDOs to get the item.value
                # Therefore, we need to adjust the item to make this work
                item['int_value'] = item.pop('value')
                assert 'value' not in item

                # Coretools is also formatting the timestamp without
                # a `Z` so we need to adjust the timestamp as well
                if 'timestamp' in item and item['timestamp'] is not None:
                    item['timestamp'] = force_to_utc(item['timestamp'])

                data = self._data_build_helper.process_serializer_data(item)
                # event can be None if stream is disabled
                if data:
                    self._data_entries.append(data)
                    self._count += 1

            # Keep track of the actual start/end incremental IDs
            self._update_incremental_id_stats(item, incremental_id)

    def _commit_stream_event_data(self):
        """
        Do a bulk commit for every event on the list
        """
        if self._event_entries:
            DataManager.bulk_create('event', self._event_entries)

    def _commit_stream_data(self):
        """
        Do a bulk commit for every data on the list
        """
        if self._data_entries:
            if self._use_firehose:
                DataManager.send_to_firehose('data', self._data_entries)
            else:
                DataManager.bulk_create('data', self._data_entries)

    def _syncup_e2_data(self):
        """
        For every stream of type E2 (Unstructured Events with Data Pointer),
        Find all associated data, and use it to update the timestamps.
        It is possible that data has not yet made it to the database,
        If so, schedule a delayed task to retry
        """
        for stream in self._event_build_helper.get_cached_streams():
            if stream and stream.enabled and stream.data_type == 'E2':
                seq_ids = []
                event_map = {}
                for event in self._event_entries:
                    # POD-1Mv2 will produce UTC synchronized device timestamps
                    # In this case, we do not need to use StreamData to sync the timestamp
                    # Note also that the mobiel app may set the timestamp even if the POD did not
                    if not event.has_utc_synchronized_device_timestamp and event.timestamp == None:
                        if event.stream_slug == stream.slug:
                            seq_id = event.incremental_id
                            seq_ids.append(seq_id)
                            event_map[seq_id] = event
                    # else we may be using V1, or it may be a V2 but with an unprocessed timestamp
                    elif not event.timestamp and bool(int(event.device_timestamp) & (1 << 31)):
                        # The event has a UTC timestamp, but has not been processed by the mobile app
                        # or tracker app
                        event.sync_utc_timestamp_from_device()

                if len(seq_ids):
                    data_qs = DataManager.filter_qs('data', stream_slug=stream.slug, extras={'int_value__in': seq_ids})
                    if data_qs.count():
                        for data in data_qs:
                            if data.int_value in event_map:
                                event = event_map.pop(data.int_value)
                                event.timestamp = parse_datetime(formatted_ts(data.timestamp))
                                event.device_timestamp = data.device_timestamp

                    # Check if there are any left over IDs and schedule delayed fixup if so
                    seq_ids = event_map.keys()
                    if len(seq_ids):
                        logger.warning('Still have {} unprocess ids. Re-schedule'.format(len(seq_ids)))
                        args = {
                            'stream_slug': stream.slug,
                            'seq_ids': list(seq_ids),
                            'attempt_count': 5
                        }
                        SyncUpE2DataAction.schedule(args=args, delay_seconds=600)

    def _update_streamer_and_streamer_report(self, base_dt_utc):
        """
        Update all records associated with this report with final updates
        a) Streamer with last_id
        b) StreamerReport with actual first/last IDs
        c) DeviceStatus record with heartbeat info

        :return: Nothing
        """

        if self._count:
            logger.info('Updating last_known_id: {} -> {}'.format(
                self._device.last_known_id, self._deserialized_data['incremental_id']
            ))

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

        elif self._streamer_report.actual_first_id == None and self._streamer_report.actual_last_id == None:
            self._streamer_report.actual_first_id = 0
            self._streamer_report.actual_last_id = 0
            self._streamer_report.save()

    def _get_base_dt_utc(self):
        """
        Compute the actual base time from the last device reset.
        This is done by subtracting the device timestamp (in sec) from the wall clock time
        we received the report. That results in a wall clock base time
        :return: base datetime in UTC
        """
        device_sent_timestamp = self._deserialized_data['device_sent_timestamp']
        assert (isinstance(device_sent_timestamp, int) and device_sent_timestamp >= 0)
        base_dt = self._received_dt - datetime.timedelta(seconds=device_sent_timestamp)
        return convert_to_utc(base_dt)

    def _set_original_first_last(self):
        """
        Initialize streamer report with the original first/last IDs
        By original, we mean the original numbers that came with the report file
        As opposed to the actual ones, which depend on what actually makes it to the db
        """
        self._streamer_report.original_first_id = self._deserialized_data['lowest_id']
        self._streamer_report.original_last_id = self._deserialized_data['highest_id']
        self._streamer_report.save()

    def process(self):
        """
        Main entry function.
        - Deserialized JSON data
        - Initialize device, streamer and streamer_report data
        - Process Event Data and commit to the database in bulk
        - Finally update streamer and streamer_report with actual IDs
        """

        start_time = time.time()

        self._initialize()
        self._all_stream_filters = {}
        self._event_entries = []
        self._data_entries = []
        self._deserialized_data = {}

        logger.info('Processing Report using ProcessReportV2JsonAction')

        assert self._fp

        factory = {
            '.json': JSONParser,
            '.mp': Python2CompatMessagePackParser
        }

        logger.info('Processing {}'.format(self._decoded_key))

        base, ext = os.path.splitext(self._decoded_key)

        if ext not in factory:
            raise WorkerInternalError('Streamer Report file extension not supported. Expected: .json or .mp')

        try:
            parser = factory[ext]()
            self._fp.seek(0)
            file_data = parser.parse(self._fp)
        except Exception as e:
            raise WorkerActionHardError('json/mp Parser errors {}'.format(str(e)))

        serializer = StreamerReportJsonPostSerializer(data=file_data)

        if serializer.is_valid():

            self._deserialized_data = serializer.validated_data

            base_dt_utc = self._get_base_dt_utc()

            self._set_original_first_last()

            self._get_device_and_streamer(
                dev_id=self._deserialized_data['device'],
                index=self._deserialized_data['streamer_index'],
                selector=self._deserialized_data['streamer_selector']
            )

            self._initialize_device()

            self._event_build_helper = StreamEventDataBuilderHelper()
            self._data_build_helper = StreamDataBuilderHelper()

            self._process_event_data()
            self._process_data()

            self._syncup_e2_data()

            self._commit_stream_event_data()
            self._commit_stream_data()

            self._update_streamer_and_streamer_report(base_dt_utc=base_dt_utc)

            # Finally, forward the streamer report to any ArchFx Cloud (if enabled)
            ForwardStreamerReportAction.schedule(args={
                'org': self._device.org.slug,
                'report': str(self._streamer_report.id),
                'ext': ext
            })

        else:
            raise WorkerActionHardError('Json Report errors {}'.format(str(serializer.errors)))

        logger.info('Time to process {0} report {1}: {2} sec'.format(
            self._count, self._streamer.slug, time.time() - start_time
        ))

        return self._count
