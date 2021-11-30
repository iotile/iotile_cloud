import datetime
import logging
import os
from urllib import parse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_datetime

from apps.physicaldevice.models import Device
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import *
from apps.streamdata.helpers import StreamDataBuilderHelper
from apps.streamdata.models import get_timestamp_from_utc_device_timestamp
from apps.streamer.models import Streamer, StreamerReport
from apps.streamer.report.parser import ParseReportException
from apps.utils.aws.s3 import download_file_from_s3, get_s3_metadata
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.data_helpers.manager import DataManager
from apps.utils.gid.convert import formatted_gdid, formatted_gsid, get_vid_from_gvid, int2did, int2vid
from apps.utils.iotile.streamer import STREAMER_SELECTOR
from apps.utils.iotile.variable import *

from .types import ENGINE_TYPES
from .worker_throtle import WorkerThrotle

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
user_model = get_user_model()
logger = logging.getLogger(__name__)


def get_utc_read_data_timestamp(base_dt, device_timestamp):
    """
    Given a device timestamp, figure about the absolute UTC datetime for a given reading.
    If most significant bit is set in the device timestamp, then it represents a time
    set by the device Real-Time Clock (RTC) and is based on seconds since 2000-01-01.
    If not, the device timestamp represents seconds since last reboot and the UTC
    is computed as a timedelta since the last reboot, represented by the base_dt

    :param base_dt: Computed base_dt to use if device_timestamp represents
                    time since last reboot. base_dt is computed based on the
                    send timestamp datetime
    :param device_timestamp: time sent by the device in the streamer report
                            It either represents seconds since last reboot
                            or if device has an RTC, then it represents time
                            since 2000-01-01
    :return: datetime representing actual time of read
    """
    if bool(int(device_timestamp) & (1 << 31)):
        # If RTC was used, the most significant bit will be set
        # to indicate this
        reading_dt = get_timestamp_from_utc_device_timestamp(device_timestamp)
    else:
        reading_dt = base_dt + datetime.timedelta(seconds=device_timestamp)

    return reading_dt


class ProcessReportBaseAction(Action):
    _use_firehose = getattr(settings, 'USE_FIREHOSE') == True
    _user = None
    _fp = None
    _device = None
    _streamer = None
    _streamer_report = None
    _received_dt = None
    _data_builder = None
    _data_entries = []
    _reboot_ids = []
    _count = 0
    _actual_first_id = None
    _actual_last_id = None
    _chopped_report = False
    _decoded_key = ''

    def _initialize(self):
        # Initialize all variables before reading report
        self._device = None
        self._streamer = None
        self._data_builder = StreamDataBuilderHelper()
        self._data_entries = []
        self._reboot_ids = []
        self._count = 0
        self._actual_first_id = None
        self._actual_last_id = None

    def _initialize_from_device_streamer(self, parser):
        assert parser

        logger.info("Verify header, footer...")
        try:
            parser.parse_header(self._fp)
            parser.parse_footer(self._fp)
        except ParseReportException as e:
            raise WorkerActionHardError(str(e))

        if parser.header['signature_flags'] != 0:
            # Currently, only support for report that have a footer that is only a hash of the report, not an HMAC
            raise WorkerActionHardError('Unrecognized signature flags')

        if not parser.check_report_hash(self._fp):
            msg = 'Invalid Report Hash: {}'.format(str(parser.header))
            logger.warning(msg)
            raise WorkerActionHardError(msg)

        self._streamer_report.original_first_id = parser.footer['lowest_id']
        self._streamer_report.original_last_id = parser.footer['highest_id']
        self._streamer_report.save()

        self._get_device_and_streamer(
            dev_id=parser.header['dev_id'],
            index=parser.header['streamer_index'],
            selector=parser.header['streamer_selector']
        )
        self._initialize_device()

        self._chopped_report = parser.chopped_off()
        if self._chopped_report:
            logger.warning('Report for {0} likely chopped off (rpt={1})'.format(
                parser.header['dev_id'], str(self._streamer_report.id)
            ))

        try:
            parser.parse_readings(self._fp)
        except ParseReportException as e:
            raise WorkerActionHardError(str(e))

    def _get_last_reboot_data_point(self):
        """
        Given a device, look for the last instance of a StreamData for a '5c00' variable (SYSTEM_VID['REBOOT']),
        which represents the last time the device was rebooted

        Note that very old objects may not have a streamer_local_id set, so search within ones
        that have a non-zero value

        :return: StreamData representing the last instance of a reset
        """
        last_item = None
        current_project = self._device.project
        assert(current_project != None)

        # variable_slug = formatted_gvid(current_project.formatted_gid, SYSTEM_VID['REBOOT'])
        try:
            reboot_data = DataManager.filter_qs('data', device_slug=self._device.slug,
                                                variable_slug__icontains=SYSTEM_VID['REBOOT'],
                                                streamer_local_id__gt=0)
        except Exception as e:
            msg = 'Query for data failed:  device={0}, variable__contain={1}'.format(self._device.slug, SYSTEM_VID['REBOOT'])
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
        if not self._device.last_known_id:
            if last_reboot and last_reboot.streamer_local_id:
                self._device.last_known_id = last_reboot.streamer_local_id
                logger.info("Device's last_known_id doesn't exist, take the lastest 5c00")
            else:
                # this is the first start in device's life time
                self._device.last_known_id = 1
                logger.info("Device's last_known_id doesn't exist, set to 1")
            self._device.save()

    def _get_device_and_streamer(self, dev_id, index, selector):
        did = int2did(dev_id)
        dev_slug = formatted_gdid(did=did)
        logger.info('Looking for Streamers using report dev ID: {0}'.format(dev_slug))
        try:
            self._device = Device.objects.get(slug=dev_slug)
            project = self._device.project
        except Device.DoesNotExist:
            raise WorkerActionHardError("Device not found in database")

        if not project:
            msg = 'Device {0} has not been claimed. Yet, it is uploading a report'.format(self._device.slug)
            raise WorkerAbortSilently(msg)

        streamers = self._device.streamers.filter(index=index)
        if streamers.count() > 1:
            msg = 'Illegal Condition. More than one Streamer for device {0}'.format(self._device.slug)
            raise WorkerActionHardError(msg)
        if streamers.count() == 0:
            # Just create a new streamer
            sg = self._device.sg
            assert sg
            process_engine_ver = sg.report_processing_engine_ver

            self._streamer = Streamer.objects.create(device=self._device,
                                                     index=index,
                                                     created_by=self._user,
                                                     process_engine_ver=process_engine_ver,
                                                     selector=selector,
                                                     is_system=selector == STREAMER_SELECTOR['SYSTEM'])
        else:
            self._streamer = streamers.first()

        if self._streamer.slug != self._streamer_report.streamer.slug:
            raise WorkerActionHardError("The streamer indicated in the streamer report doesn't correspond to the streamer slug of the streamer report in database\n"
                                        "Streamer found by report' header : {}\n"
                                        "Streamer registered by streamer report: {}".format(self._streamer.slug, self._streamer_report.streamer.slug))

    def _update_incremental_id_stats(self, item, incremental_id):
        """
        Keep track of the first and last incremental_id we see.

        :param item: Report reading item
        :param incremental_id: Current incremental id
        :return: Nothing. Setting class local variables
        """
        if not self._actual_first_id:
            self._actual_first_id = incremental_id
        self._actual_last_id = incremental_id

    def _read_stream_data(self, parser, base_dt):
        project = self._device.project
        pid = project.formatted_gid
        did = self._device.formatted_gid

        original_first_id = parser.footer['lowest_id']
        original_last_id = parser.footer['highest_id']

        for item in parser.data:
            incremental_id = item['id']
            assert (incremental_id >= original_first_id or incremental_id <= original_last_id)
            assert(incremental_id is not None and isinstance(incremental_id, int))

            if incremental_id > self._streamer.last_id:
                vid = int2vid(item['stream'])
                stream_slug = formatted_gsid(pid=pid, did=did, vid=vid)
                value = item['value']
                device_timestamp = item['timestamp']
                assert device_timestamp is not None and isinstance(device_timestamp, int)
                # Check if device_timestamp represents an absolute UTC timestamp or
                # time since reboot, and return an absolute UTC datetime
                reading_dt = get_utc_read_data_timestamp(base_dt, device_timestamp)

                assert value is not None and isinstance(value, int)

                stream_data = self._data_builder.build_data_obj(stream_slug=stream_slug,
                                                                streamer_local_id=incremental_id,
                                                                device_timestamp=device_timestamp,
                                                                timestamp=reading_dt,
                                                                int_value=value)
                assert (stream_data.int_value != None)
                assert (stream_data.int_value == value)

                # Keep track of the actual start/end incremental IDs
                self._update_incremental_id_stats(item, incremental_id)

                if self._data_builder.check_if_stream_is_enabled(stream_data.stream_slug):
                    self._data_entries.append(stream_data)
                    self._count += 1
                if get_vid_from_gvid(stream_data.variable_slug) == SYSTEM_VID['REBOOT']:
                    logger.info('Found Reboot: {}: {}'.format(stream_slug, self._actual_last_id))
                    self._reboot_ids.append(stream_data.streamer_local_id)

    def _commit_stream_data(self, parser):

        # 1. Add an entry to the stream representing read reports
        #    This is used to help us confirm that the data has made it to RedShift

        if self._count:
            if self._chopped_report:
                streamer_data_slug = formatted_gsid(pid=self._device.project.formatted_gid, did=self._device.formatted_gid, vid=SYSTEM_VID['CHOPPED_REPORT'])
                streamer_data_point = self._data_builder.build_data_obj(stream_slug=streamer_data_slug,
                                                                        streamer_local_id=parser.header['rpt_id'],
                                                                        status='cln',
                                                                        device_timestamp=parser.header['sent_timestamp'],
                                                                        timestamp=self._received_dt,
                                                                        int_value=self._streamer.index)
            else:
                streamer_data_slug = formatted_gsid(pid=self._device.project.formatted_gid, did=self._device.formatted_gid, vid=SYSTEM_VID['COMPLETE_REPORT'])
                streamer_data_point = self._data_builder.build_data_obj(stream_slug=streamer_data_slug,
                                                                        streamer_local_id=parser.header['rpt_id'],
                                                                        status='cln',
                                                                        device_timestamp=parser.header['sent_timestamp'],
                                                                        timestamp=self._received_dt,
                                                                        int_value=self._streamer.index)
            self._data_entries.append(streamer_data_point)

        # 2. Do a batch update to send all stream data to the database
        if self._count and (self._actual_first_id != None) and (self._actual_last_id != None):
            if self._use_firehose:
                DataManager.send_to_firehose('data', self._data_entries)
            else:
                DataManager.bulk_create('data', self._data_entries)

    def process(self):
        raise WorkerInternalError('Derived object must implement')

    def execute(self, arguments):
        super(ProcessReportBaseAction, self).execute(arguments)
        if 'bucket' in arguments and 'key' in arguments:
            bucket = arguments['bucket']
            key = arguments['key']
            self._decoded_key = parse.unquote(key)
            try:
                self._fp = download_file_from_s3(bucket, self._decoded_key)
            except Exception as e:
                # We don't know what kind of exceptions can be thrown, so catch all, but only because we are trying
                # a single command
                raise WorkerActionHardError('Error: {0}. Incorrect report in bucket {1}, key : {2}'.format(str(e), bucket, key))

            try:
                metadata = get_s3_metadata(bucket, key)
                logger.info('metadata: {}'.format(metadata))
                # user_slug = metadata['x-amz-meta-user']
                received_ts = metadata['x-amz-meta-sent']
                # streamer_slug = metadata['x-amz-meta-streamer']
                report_id = metadata['x-amz-meta-uuid']
            except Exception as e:
                if getattr(settings, 'SERVER_TYPE') == 'dev':
                    # If we are not using s3, decode information from s3 key
                    info = self._decoded_key.split('/')
                    try:
                        # streamer_slug=info[1]
                        received_ts = '{y}-{m}-{d}T{h}:00:00Z'.format(y=info[2], m=info[3], d=info[4], h=info[5])
                        streamer_report_name = info[-1]
                        report_id = streamer_report_name.split('.')[0]
                    except IndexError as e:
                        raise WorkerActionHardError('Error: {0}. Incorrect key format in payload with bucket {1}, key : {2}'.format(str(e), bucket, key))

                    metadata = info
                else:
                    raise WorkerActionHardError('Error: {0}. path: //{1}/{2}'.format(str(e), bucket, key))
            try:
                self._received_dt = parse_datetime(received_ts)
                self._streamer_report = StreamerReport.objects.get(id=report_id)
                self._user = self._streamer_report.created_by
            except user_model.DoesNotExist:
                raise WorkerActionHardError('User does not exist. Incorrect report in bucket {}, key : {}'.format(bucket, key))
            except StreamerReport.DoesNotExist:
                raise WorkerActionHardError("Streamer report {0} not found!".format(report_id))

            if not self._received_dt:
                raise WorkerActionHardError('Received date time in key is not valid. Incorrect timestamp in bucket {0}, key : {1}'.format(bucket, key))

            # We want to ensure that we never process any given streamer in parallel, as it can cause race conditions (i.e. duplicates)
            # We use the Redis cache to ensure we handle streamer work as atomic operations

            throtle_helper = WorkerThrotle(self, self._streamer_report.streamer.slug)
            if throtle_helper.begin_process():
                try:
                    self.process()
                except WorkerActionHardError as e:
                    raise WorkerActionHardError(e)
                except Exception as e:
                    raise e
                finally:
                    throtle_helper.end_process()

            else:
                ProcessReportBaseAction.schedule(args=arguments, delay_seconds=120)
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

        if 'bucket' in args and 'key' in args:
            base, ext = os.path.splitext(args['key'])

            if 'version' in args and args['version'] in ENGINE_TYPES:
                if args['version'] not in ENGINE_TYPES:
                    raise WorkerActionHardError('Unsupported Streamer Report Version: {}'.format(args['version']))
                if ext not in ENGINE_TYPES[args['version']]:
                    raise WorkerActionHardError('Unsupported file extension ({}) for Streamer Report V{}'.format(ext, args['version']))
                module_name = ENGINE_TYPES[args['version']][ext]['module_name']
                class_name = ENGINE_TYPES[args['version']][ext]['class_name']
            else:
                module_name = ENGINE_TYPES['v0']['.bin']['module_name']
                class_name = ENGINE_TYPES['v0']['.bin']['class_name']

            logger.info('Using module_name={0}, class_name={1}'.format(module_name, class_name))

            super(ProcessReportBaseAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
        else:
            raise WorkerActionHardError('Missing fields in argument payload.\nReceived args: {}\nRequired args : bucket, key'.format(args))
