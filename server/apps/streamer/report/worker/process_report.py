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
from apps.streamer.report.parser import ParseReportException, ReportParser
from apps.streamer.report.worker.handle_delay import HandleDelayAction
from apps.streamer.report.worker.handle_reboot import HandleRebootAction
from apps.streamfilter.cache_utils import cached_serialized_filter_for_slug
from apps.streamfilter.process import FilterHelper
from apps.utils.aws.s3 import download_file_from_s3
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.data_helpers.manager import DataManager
from apps.utils.gid.convert import formatted_gdid, formatted_gsid, get_vid_from_gvid, int2did, int2vid
from apps.utils.iotile.streamer import STREAMER_SELECTOR
from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.timezone_utils import convert_to_utc, str_utc

from .streamer_worker_throtle import StreamerWorkerThrotle

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
user_model = get_user_model()
logger = logging.getLogger(__name__)
RETRY_DELAY_SECONDS = 60 * 5  # in seconds


def download_streamer_report_from_s3(bucket, key):
    return download_file_from_s3(bucket=bucket, key=key)


class ProcessReportAction(Action):
    use_firehose = False
    user = None
    fp = None
    device = None
    streamer = None
    received_dt = None
    streamer_report = None
    data_entries = []
    count = 0
    actual_first_id = None
    actual_last_id = None
    last_user_incremental_id = None
    last_system_incremental_id = None
    reboot_ids = []
    all_stream_filters = {}
    helper = None

    def initialize(self):
        # Initialize all variables before reading report
        self.device = None
        self.streamer = None
        self.data_entries = []
        self.count = 0
        self.actual_first_id = None
        self.actual_last_id = None
        self.last_user_incremental_id = None
        self.last_system_incremental_id = None
        self.reboot_ids = []
        self.all_stream_filters = {}
        self.helper = StreamDataBuilderHelper()

    def _handle_reboot(self, parser):
        logger.info('Reboot detected during processing. Scheduling handle reboot action...')
        logger.info("Reboot ids: {}".format(self.reboot_ids))
        reboot_args = {
            'device_slug': self.device.slug,
            'project_id': str(self.device.project.id),
            'block_end_id': parser.header['rpt_id'],  # end of block
            'block_start_id': self.device.last_known_id,  # start of block
            'reboot_ids': self.reboot_ids
        }
        HandleRebootAction.schedule(args=reboot_args, delay_seconds=RETRY_DELAY_SECONDS)

    def _handle_delay_report(self):
        delay_args = {
            'device_slug': self.device.slug,
            'project_id': str(self.device.project.id),
            'start_id': self.streamer_report.actual_first_id,
            'end_id': self.streamer_report.actual_last_id,
            'report_id': str(self.streamer_report.id)
        }
        HandleDelayAction.schedule(args=delay_args, delay_seconds=RETRY_DELAY_SECONDS)

    def _get_device_and_streamer(self, parser, dev_id):
        did = int2did(dev_id)
        dev_slug = formatted_gdid(did=did)
        logger.info('Looking for Streamers using report dev ID: {0}'.format(dev_slug))
        try:
            self.device = Device.objects.get(slug=dev_slug)
            project = self.device.project
        except Device.DoesNotExist:
            raise WorkerActionHardError("Device not found in database")
        if not project:
            msg = 'Device {0} has not been claimed. Yet, it is uploading a report'.format(self.device.slug)
            logger.warning(msg)
            raise WorkerActionHardError(msg)

        streamer_index = parser.header['streamer_index']
        streamers = self.device.streamers.filter(index=streamer_index)
        if streamers.count() > 1:
            msg = 'Illegal Condition. More than one Streamer for device {0}'.format(self.device.slug)
            raise WorkerActionHardError(msg)
        if streamers.count() == 0:
            # Just create a new streamer
            sg = self.device.sg
            assert sg
            process_engine_ver = sg.report_processing_engine_ver

            self.streamer = Streamer.objects.create(device=self.device,
                                                    index=streamer_index,
                                                    created_by=self.user,
                                                    process_engine_ver=process_engine_ver,
                                                    selector=parser.header['streamer_selector'],
                                                    is_system=parser.header['streamer_selector'] == STREAMER_SELECTOR['SYSTEM'])
        else:
            self. streamer = streamers.first()
        if not self.streamer.slug == self.streamer_report.streamer.slug:
            raise WorkerActionHardError("The streamer indicated in the streamer report doesn't correspond to the streamer slug of the streamer report in database\n"
                                        "Streamer found by report' header : {}\n"
                                        "Streamer registered by streamer report: {}".format(self.streamer.slug, self.streamer_report.streamer.slug))

        # TODO: This function should not be needed, as it looks like it was a bug related to
        # ReportProcessorAndUploadToS3._get_device_and_streamer previously creating a streamer
        # with is_system = selector == 0x3fff instead of 0x5fff
        # Leave for now, as it is harmless, but should be cleaned up once we confirm
        self.streamer.update_type_if_needed(parser.header['streamer_selector'])

    def _update_incremental_id_stats(self, item, incremental_id):
        """
        Keep track of the first and last incremental_id we see.
        Also keep track of this for both user and system reports.

        :param item: Report reading item
        :param incremental_id: Current incremental id
        :return: Nothing. Setting class local variables
        """
        if not self.actual_first_id:
            self.actual_first_id = incremental_id
        self.actual_last_id = incremental_id
        if bool(item['stream'] & (1 << 11)):
            self.last_system_incremental_id = incremental_id
        else:
            self.last_user_incremental_id = incremental_id

    def _read_stream_data(self, parser, base_dt):
        project = self.device.project
        pid = project.formatted_gid
        did = self.device.formatted_gid

        original_first_id = parser.footer['lowest_id']
        original_last_id = parser.footer['highest_id']

        for item in parser.data:
            incremental_id = item['id']
            assert (incremental_id >= original_first_id or incremental_id <= original_last_id)
            assert(incremental_id is not None and isinstance(incremental_id, int))

            if incremental_id > self.streamer.last_id:
                vid = int2vid(item['stream'])
                stream_slug = formatted_gsid(pid=pid, did=did, vid=vid)
                value = item['value']
                point_timestamp = item['timestamp']
                reading_dt = base_dt + datetime.timedelta(seconds=point_timestamp)
                assert (value is not None and isinstance(value, int))

                stream_data = self.helper.build_data_obj(stream_slug=stream_slug,
                                                         streamer_local_id=incremental_id,
                                                         device_timestamp=point_timestamp,
                                                         timestamp=reading_dt,
                                                         int_value=value)
                assert (stream_data.int_value != None)
                assert (stream_data.int_value == value)

                # Keep track of the actual start/end incremental IDs
                self._update_incremental_id_stats(item, incremental_id)

                if self.helper.check_if_stream_is_enabled(stream_data.stream_slug):
                    self.data_entries.append(stream_data)
                    self.count += 1
                if get_vid_from_gvid(stream_data.variable_slug) == SYSTEM_VID['REBOOT']:
                    self.reboot_ids += [stream_data.streamer_local_id]

    def _post_process_stream_data(self):
        """
        Do any post-processing:
        a) Check filters apply and if so, create a single filter per stream

        :return: Nothing
        """
        if self.count and (self.actual_first_id != None) and (self.actual_last_id != None):

            for stream in self.helper.get_cached_streams():
                if stream:
                    stream_slug = stream.slug
                    if stream_slug not in self.all_stream_filters:
                        # "expensive" call, call once for each stream in the report
                        self.all_stream_filters[stream_slug] = cached_serialized_filter_for_slug(stream_slug)

    def _commit_stream_data(self, parser):

        # 1. Add an entry to the stream representing read reports
        #    This is used to help us confirm that the data has made it to RedShift

        if self.count:
            streamer_data_slug = formatted_gsid(pid=self.device.project.formatted_gid, did=self.device.formatted_gid, vid=SYSTEM_VID['COMPLETE_REPORT'])
            streamer_data_point = self.helper.build_data_obj(stream_slug=streamer_data_slug,
                                                             streamer_local_id=parser.header['rpt_id'],
                                                             device_timestamp=parser.header['sent_timestamp'],
                                                             timestamp=self.received_dt,
                                                             int_value=self.streamer.index)
            self.data_entries.append(streamer_data_point)

        # 2. Do a batch update to send all stream data to the database
        if self.count and (self.actual_first_id != None) and (self.actual_last_id != None):
            if self.use_firehose:
                DataManager.send_to_firehose('data', self.data_entries)
            else:
                DataManager.bulk_create('data', self.data_entries)

    def _update_streamer_and_streamer_report(self, parser, base_dt_utc):
        """
        Update all records associated with this report with final updates
        a) Streamer with last_id
        b) StreamerReport with actual first/last IDs
        c) DynamoDb record with heartbeat info

        :return: Nothing
        """

        if self.count:
            logger.info('Updating last_known_id: {} -> {}'.format(self.device.last_known_id, parser.header['rpt_id']))
            device_status = DeviceStatus.get_or_create(self.device)

            with transaction.atomic():
                self.streamer_report.actual_first_id = self.actual_first_id
                self.streamer_report.actual_last_id = self.actual_last_id
                self.streamer_report.save()
                self.streamer.last_id = self.streamer_report.actual_last_id
                self.streamer.last_reboot_ts = base_dt_utc
                self.streamer.save()
                # Update Device Status for Hearthbeat notifications
                if self.streamer_report.actual_last_id > device_status.last_known_id:
                    device_status.last_known_id = self.streamer_report.actual_last_id
                    device_status.save()

        elif self.streamer_report.actual_first_id == None and self.streamer_report.actual_last_id == None:
            self.streamer_report.actual_first_id = 0
            self.streamer_report.actual_last_id = 0
            self.streamer_report.save()

    def _schedule_additional_tasks(self, parser):
        """
        Process or schedule any additional tasks, like fixing reboots, update data status, etc.

        :return: Nothing
        """
        if self.count:
            if self.streamer.is_system:
                logger.info('Post processing for system report.')
                if len(self.reboot_ids) > 0:
                    self._handle_reboot(parser)
            else:
                lastest_reboot = self._get_last_reboot_data_point()
                if lastest_reboot and lastest_reboot.streamer_local_id:
                    if self.actual_first_id < lastest_reboot.streamer_local_id:
                        logger.info("Delayed report detected, scheduling HandleDelayAction...")
                        self._handle_delay_report()

            if self.streamer.is_system:
                self.device.last_known_id = parser.header['rpt_id']
                self.device.save()

    def _get_last_reboot_data_point(self):
        """
        Given a device, look for the last instance of a StreamData for a '5c00' variable (REBOOT_VID),
        which represents the last time the device was rebooted

        Note that very old objects may not have a streamer_local_id set, so search within ones
        that have a non-zero value

        :param device: device in question
        :return: StreamData representing the last instance of a reset
        """
        last_item = None
        current_project = self.device.project
        assert(current_project != None)

        # variable_slug = formatted_gvid(current_project.formatted_gid, REBOOT_VID)
        try:
            reboot_data = DataManager.filter_qs('data', device_slug=self.device.slug,
                                                variable_slug__icontains=SYSTEM_VID['REBOOT'],
                                                streamer_local_id__gt=0)
        except Exception as e:
            msg = 'Query for data failed:  device={0}, variable__contain={1}'.format(self.device.slug, SYSTEM_VID['REBOOT'])
            msg += '\n\n{}'.format(str(e))
            logger.warning(msg)
            sns_staff_notification(msg)
            reboot_data = None

        if reboot_data:
            last_item = reboot_data.order_by('-streamer_local_id').first()

        return last_item

    def _initialize_device(self):
        # Find the last time the device was reseted, if available
        last_reboot = self._get_last_reboot_data_point()
        if not self.device.last_known_id:
            if last_reboot and last_reboot.streamer_local_id:
                self.device.last_known_id = last_reboot.streamer_local_id
                logger.info("Device's last_known_id doesn't exist, take the lastest 5c00")
            else:
                # this is the first start in device's life time
                self.device.last_known_id = 1
                logger.info("Device's last_known_id doesn't exist, set to 1")
                self.device.save()

    def process(self):
        start_time = time.time()
        parser = ReportParser()

        self.initialize()

        logger.info("Verify header, footer...")
        try:
            parser.parse_header(self.fp)
            parser.parse_footer(self.fp)
        except ParseReportException as e:
            raise WorkerActionHardError(str(e))

        if parser.header['signature_flags'] != 0:
            # Currently, only support for report that have a footer that is only a hash of the report, not an HMAC
            raise WorkerActionHardError('Unrecognized signature flags')

        if not parser.check_report_hash(self.fp):
            msg = 'Invalid Report Hash: {}'.format(str(parser.header))
            logger.warning(msg)
            raise WorkerActionHardError(msg)

        sent_timestamp = parser.header['sent_timestamp']
        assert (isinstance(sent_timestamp, int) and sent_timestamp >= 0)
        base_dt = self.received_dt - datetime.timedelta(seconds=sent_timestamp)
        base_dt_utc = convert_to_utc(base_dt)

        self.streamer_report.original_first_id = parser.footer['lowest_id']
        self.streamer_report.original_last_id = parser.footer['highest_id']
        self.streamer_report.save()

        self._get_device_and_streamer(parser=parser, dev_id=parser.header['dev_id'])
        self._initialize_device()

        if parser.chopped_off():
            logger.warning('Report for {0} likely chopped off (rpt={1})'.format(
                parser.header['dev_id'], str(self.streamer_report.id)
            ))

        try:
            parser.parse_readings(self.fp)
        except ParseReportException as e:
            raise WorkerActionHardError(str(e))

        # 1. Parse readings from report
        self._read_stream_data(base_dt=base_dt, parser=parser)

        # 1.5. Ensure this is not a V2 selector
        if parser.header['streamer_selector'] == STREAMER_SELECTOR['USER']:
            raise WorkerActionHardError('Unexpected selector for V0 engine: {}'.format(hex(STREAMER_SELECTOR['USER'])))

        # 2. Do any post-processing on the array of data data_entries
        self._post_process_stream_data()

        # 3. Commit all stream data data_entries
        self._commit_stream_data(parser=parser)

        # 4. Update all associated records (e.g. streamer and streamer report)
        self._update_streamer_and_streamer_report(parser=parser, base_dt_utc=base_dt_utc)

        # 5. Schedule any additional tasks (e.g. update status, fix reboots, etc.)
        if self.count:
            self._schedule_additional_tasks(parser=parser)

            # Process filters here, but this is actually wrong as we are processing before
            # fixing any reboots TODO: Fix this
            filter_helper = FilterHelper()
            filter_helper.process_filter_report(self.data_entries, self.all_stream_filters)

        logger.info('Time to process {0} report {1}: {2} sec'.format(self.count, self.streamer.slug, time.time() - start_time))
        return self.count

    def execute(self, arguments):
        super(ProcessReportAction, self).execute(arguments)
        if 'bucket' in arguments and 'key' in arguments:
            bucket = arguments['bucket']
            key = arguments['key']
            decoded_key = parse.unquote(key)
            info = decoded_key.split('/')
            self.use_firehose = getattr(settings, 'USE_FIREHOSE') == True
            try:
                self.fp = download_streamer_report_from_s3(bucket, decoded_key)
            except Exception as e:
                # We don't know what kind of exceptions can be thrown, so catch all, but only because we are trying
                # a single command
                raise WorkerActionHardError('Error: {0}. Incorrect report in bucket {1}, key : {2}'.format(str(e), bucket, key))

            try:
                self.user = user_model.objects.get(slug=info[1])
                self.received_dt = parse_datetime(info[2])
                streamer_report_name = info[3]
                streamer_report_id = streamer_report_name.split('.')[0]
                self.streamer_report = StreamerReport.objects.get(id=streamer_report_id)
            except user_model.DoesNotExist:
                raise WorkerActionHardError('User does not exist. Incorrect report in bucket {}, key : {}'.format(bucket, key))
            except IndexError as e:
                raise WorkerActionHardError('Error: {0}. Incorrect key format in payload with bucket {1}, key : {2}'.format(str(e), bucket, key))
            except StreamerReport.DoesNotExist:
                raise WorkerActionHardError("Streamer report {} not found !".format(info[3]))

            if not self.received_dt:
                raise WorkerActionHardError('Received date time in key is not valid. Incorrect timestamp in bucket {0}, key : {1}'.format(bucket, key))

            # We want to ensure that we never process any given streamer in parallel, as it can cause race conditions (i.e. duplicates)
            # We use the Redis cache to ensure we handle streamer work as atomic operations

            throtle_helper = StreamerWorkerThrotle(self, self.streamer_report.streamer.slug)
            if throtle_helper.begin_process():
                try:
                    self.process()
                except WorkerActionHardError as e:
                    throtle_helper.end_process()
                    raise WorkerActionHardError(e)
                except Exception as e:
                    throtle_helper.end_process()
                    raise e

                throtle_helper.end_process()
            else:
                ProcessReportAction.schedule(args=arguments, delay_seconds=RETRY_DELAY_SECONDS)
        else:
            raise WorkerActionHardError('Bucket and/or key not found in arguments. Error comes from task: {}'.format(arguments))

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
        if 'bucket' in args and 'key' in args:
            super(ProcessReportAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
        else:
            raise WorkerActionHardError('Missing fields in argument payload.\nReceived args: {}\nRequired args : bucket, key'.format(args))
