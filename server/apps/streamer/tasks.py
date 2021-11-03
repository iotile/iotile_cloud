import logging
import datetime
import time
import os
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone

from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser

from iotile_cloud.utils.gid import IOTileDeviceSlug

from apps.utils.gid.convert import formatted_gdid, int2did
from apps.physicaldevice.models import Device, DeviceStatus
from apps.utils.timezone_utils import convert_to_utc
from apps.utils.aws.s3 import upload_blob
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.timezone_utils import str_utc

from .models import Streamer, get_streamer_error_s3_bucket_name
from .report.parser import ReportParser, ParseReportException
from .worker.common.base_action import ProcessReportBaseAction
from .serializers import StreamerReportJsonV2PostSerializer
from .msg_pack import Python2CompatMessagePackParser

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')

logger = logging.getLogger(__name__)
PRODUCTION = getattr(settings, 'PRODUCTION')
SERVER_TYPE = getattr(settings, 'SERVER_TYPE')
TESTING = getattr(settings, 'TESTING')


def upload_report(bucket, key, blob, metadata=None):
    if not TESTING:
        try:
            upload_blob(bucket=bucket, key=key, blob=blob, metadata=metadata)
        except Exception as e:
            logger.error('Failed to upload report: {}'.format(e))
            raise e
    else:
        logger.info('Skipping streamer report upload (not production)')

def upload_incorrect_streamer_report_to_s3(streamer, fp, e=None, user=None):
    fp.seek(0)
    bucket = get_streamer_error_s3_bucket_name()
    if streamer:
        # upload file under given streamer's error directory if we managed to at least parse header
        key = streamer.get_error_s3_key()
    else:
        # otherwise, upload under global error directory
        now = datetime.datetime.utcnow()
        ts = now.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        key_format = getattr(settings, 'STREAMER_S3_KEY_FORMAT')
        if user:
            error_relative_key = '{0}--{1}'.format(ts, user.slug)
        else:
            error_relative_key = '{0}'.format(ts)
        key = key_format.format(slug='errors/{}'.format(now.strftime('%Y')), uuid=error_relative_key)

    logger.info('Uploading INCORRECT streamer report to {0}:{1}'.format(bucket, key))
    upload_report(bucket=bucket, key=key, blob=fp)
    msg = 'Incorrect streamer report\nINCORRECT streamer report saved to {0}:{1}'.format(bucket, key)
    if e:
        msg += '\n\n' + e
    sns_staff_notification(msg)


class ProcessReportException(Exception):
    def __init__(self, msg):
        logger.debug("ReportProcess error with message: {0}".format(msg))
        raise ValidationError(msg)


class ReportUploaderAndProcessScheduler(object):
    """
    Verify header, footer then upload report to S3
    """
    def __init__(self, request, received_dt, fp):
        self.fp = fp
        self.received_dt = convert_to_utc(received_dt)
        self.user = request.user
        self.use_firehose = getattr(settings, 'USE_FIREHOSE') == True

    def _handle_error(self, msg, streamer=None):
        logger.error(msg)
        upload_incorrect_streamer_report_to_s3(streamer, self.fp, e=msg, user=self.user)
        raise ProcessReportException(msg=msg)

    def _check_base_dt(self, device, base_dt_utc, device_sent_timestamp):
        if base_dt_utc > timezone.now() + datetime.timedelta(hours=1):
            msg = 'Base time computation error: base_dt={0}, sent_timestamp={1}'.format(base_dt_utc,
                                                                                        device_sent_timestamp)
            msg += '\n\nCurrent time is {0} (+1h error margin)'.format(timezone.now())
            msg += 'received_dt = {}\n'.format(self.received_dt)
            msg += 'sent_timestamp = {}\n'.format(device_sent_timestamp)
            msg += 'dev_id = {}\n'.format(device.slug)
            if self.user:
                msg += 'user = {}\n'.format(self.user.username)
            sns_staff_notification(msg)
            if not(settings.PRODUCTION or settings.DOCKER):
                self._handle_error(msg)

    def _get_dropbox_s3_bucket_and_key(self, streamer_report, ext):
        # For now, V0 still uses the old S3 naming scheme, while V1+ uses the new one
        streamer = streamer_report.streamer
        if streamer.process_engine_ver == 0:
            bucket = getattr(settings, 'STREAMER_REPORT_DROPBOX_BUCKET_NAME')
            dropbox_key_format = getattr(settings, 'STREAMER_REPORT_DROPBOX_KEY_FORMAT')
            key_path = dropbox_key_format.format(username=self.user.slug, date=str_utc(self.received_dt))
            key = key_path + '/' + str(streamer_report.id) + ext
        else:
            bucket, key = streamer_report.get_dropbox_s3_bucket_and_key(ext)
        return bucket, key

    def _create_streamer(self, device, process_engine_ver, index, selector):
        """
        Create a new streamer. Use the device SG to get the report
        processing engine version.

        :param device: Device to create streamer for
        :process_engine_ver: Integer representing process engine version
        :index: Streamer Index
        :selector: Streamer Selector
        :return: New Streamer Record
        """

        streamer = Streamer.objects.create(device=device,
                                           index=index,
                                           process_engine_ver=process_engine_ver,
                                           selector=selector,
                                           created_by=self.user)

        return streamer

    def _get_device_and_streamer(self, dev_id, index, selector):
        did = int2did(dev_id)
        dev_slug = formatted_gdid(did=did)
        logger.info('Looking for Streamers using report dev ID: {0}'.format(dev_slug))

        device = get_object_or_404(Device, slug=dev_slug)
        project = device.project
        if not project:
            msg = 'Device {0} has not been claimed. Yet, it is uploading a report'.format(device.slug)
            self._handle_error(msg)

        sg = device.sg
        assert sg
        process_engine_ver = sg.report_processing_engine_ver

        streamers = device.streamers.filter(index=index)
        if streamers.count() > 1:
            msg = 'Illegal Condition. More than one Streamer for device {0}'.format(device.slug)
            self._handle_error(msg)
        if streamers.count() == 0:
            # Just create a new streamer
            streamer = self._create_streamer(device, process_engine_ver, index, selector)
        else:
            streamer = streamers.first()
            # Double check that the process_engine version is up to date
            if streamer.process_engine_ver != process_engine_ver:
                streamer.process_engine_ver = process_engine_ver
                streamer.save()
            if not streamer.selector:
                # TODO: This can be removed in the future once it is confirmed all streamers have a selector
                streamer.selector = selector
                streamer.save()

        return device, streamer

    def _upload_report(self, streamer_report, ext):
        bucket, key = self._get_dropbox_s3_bucket_and_key(streamer_report=streamer_report, ext=ext)

        # Get streamer report metadata that we want to set on S3
        metadata = streamer_report.get_s3_metadata()

        try:
            self.fp.seek(0)
            try:
                upload_report(bucket=bucket, key=key, blob=self.fp, metadata=metadata)
            except Exception as e:
                raise ProcessReportException(msg=str(e))
        except Exception as e:
            self._handle_error(str(e))

        return bucket, key

    def _process_bin_file(self, serializer):
        """
        This is to be called for IOTile Coretool based binary Streamer Report files
        Checking the validity of footer, header, signature then if success upload file to S3
        Also ensure there is a streamer record and create a streamer report record for this report
        :param serializer:
        :return:
        """

        # Do a quick Parse to ensure the report is valid
        parser = ReportParser()
        try:
            parser.parse_header(self.fp)
            parser.parse_footer(self.fp)
        except ParseReportException as e:
            self._handle_error(e, None)

        if parser.header['signature_flags'] != 0:
            # Currently, only support for report that have a footer that is only a hash of the report, not an HMAC
            self._handle_error('Unrecognized signature flags (user={})'.format(self.user))

        if not parser.check_report_hash(self.fp):
            slug = IOTileDeviceSlug(parser.header['dev_id'])
            self._handle_error('Invalid Hash: {} (idx={}, user={})'.format(
                str(slug), parser.header['streamer_index'], self.user
            ))

        device_sent_timestamp = parser.header['sent_timestamp']
        assert isinstance(device_sent_timestamp, int) and device_sent_timestamp >= 0
        base_dt = self.received_dt - datetime.timedelta(seconds=device_sent_timestamp)
        dev_id = parser.header['dev_id']

        # check validity of device and streamer
        device, streamer = self._get_device_and_streamer(
            dev_id=dev_id,
            index=parser.header['streamer_index'],
            selector=parser.header['streamer_selector']
        )

        base_dt_utc = convert_to_utc(base_dt)
        self._check_base_dt(device=device, base_dt_utc=base_dt_utc, device_sent_timestamp=device_sent_timestamp)

        streamer_report = serializer.save(streamer=streamer,
                                          sent_timestamp=self.received_dt,
                                          device_sent_timestamp=device_sent_timestamp,
                                          incremental_id=parser.header['rpt_id'],
                                          created_by=self.user)

        return {
            'device': device,
            'streamer': streamer,
            'streamer_report': streamer_report,
            'expected_count': parser.expected_count
        }

    def _process_json(self, data, serializer):
        """
        This is to be called for Virtual Json based streamer report files

        :param data: validated data
        :param serializer: Required serializer to create StreamerReport
        :return: Dict with device, streamer, streamer_report and expected_count
        """
        device = streamer = streamer_report = None
        count = 0

        device_sent_timestamp = data['device_sent_timestamp']
        assert isinstance(device_sent_timestamp, int) and device_sent_timestamp >= 0
        base_dt = self.received_dt - datetime.timedelta(seconds=device_sent_timestamp)

        # check validity of device and streamer
        device, streamer = self._get_device_and_streamer(
            dev_id=data['device'],
            index=data['streamer_index'],
            selector=data['streamer_selector']
        )

        base_dt_utc = convert_to_utc(base_dt)
        self._check_base_dt(device=device,
                            base_dt_utc=base_dt_utc,
                            device_sent_timestamp=device_sent_timestamp)

        streamer_report = serializer.save(streamer=streamer,
                                          sent_timestamp=self.received_dt,
                                          incremental_id=data['incremental_id'],
                                          created_by=self.user)

        if 'events' in data:
            count += len(data['events'])
        if 'data' in data:
            count += len(data['data'])

        return {
            'device': device,
            'streamer': streamer,
            'streamer_report': streamer_report,
            'expected_count': count
        }

    def _process_json_file(self, serializer):
        """
        This is to be called for Virtual Json based streamer report files

        :param serializer: Required serializer to create StreamerReport
        :return: Dict with device, streamer, streamer_report and expected_count
        """

        try:
            parser = JSONParser()
            file_data = parser.parse(self.fp)
        except Exception as e:
            raise ProcessReportException(msg='JSON parsing error: {}'.format(e))

        file_serializer = StreamerReportJsonV2PostSerializer(data=file_data)

        if file_serializer.is_valid(raise_exception=True):

            return self._process_json(file_serializer.validated_data, serializer)

        return {
            'device': None,
            'streamer': None,
            'streamer_report': None,
            'expected_count': 0
        }

    def _process_msgpack_file(self, serializer):
        """
        This is to be called for Virtual MessagePack based streamer report files

        :param serializer: Required serializer to create StreamerReport
        :return: Dict with device, streamer, streamer_report and expected_count
        """

        try:
            parser = Python2CompatMessagePackParser()
            file_data = parser.parse(self.fp)
        except Exception as e:
            raise ProcessReportException(msg='JSON parsing error: {}'.format(e))

        file_serializer = StreamerReportJsonV2PostSerializer(data=file_data)

        if file_serializer.is_valid(raise_exception=True):
            return self._process_json(file_serializer.validated_data, serializer)

        return {
            'device': None,
            'streamer': None,
            'streamer_report': None,
            'expected_count': 0
        }

    def process(self, serializer, filename):
        """

        :param serializer: Serializer from DRF View. To be used to serialize POST body, if any
        :param filename: filename of attached file
        :return:
        """
        start_time = time.time()

        factory = {
            '': self._process_bin_file, # For Backwards compatibility (Issue-1125)
            '.bin': self._process_bin_file,
            '.json': self._process_json_file,
            '.mp': self._process_msgpack_file
        }

        base, ext = os.path.splitext(filename)

        if ext not in factory:
            raise ProcessReportException(msg='Streamer Report file extension not supported. Expected: .bin, .json or .mp')

        report_info = factory[ext](serializer)

        device = report_info['device']
        streamer = report_info['streamer']
        streamer_report = report_info['streamer_report']

        assert device and streamer and streamer_report

        # Update Device Status for Heartbeat notifications
        status = DeviceStatus.get_or_create(device)
        status.update_health(self.received_dt)

        # Upload report to S3 and then schedule processing
        if settings.TESTING:
            bucket, key = self._get_dropbox_s3_bucket_and_key(streamer_report=streamer_report, ext=ext)
        else:
            bucket, key = self._upload_report(streamer_report=streamer_report, ext=ext)

        try:
            args = {
                'version': 'v{}'.format(streamer.process_engine_ver),
                'streamer': streamer.slug,
                'bucket': bucket,
                'key': key
            }
            # pprint(args)
            ProcessReportBaseAction.schedule(args=args)
        except Exception as e:
            self._handle_error(str(e))

        # returning expected_count for now
        logger.info('Data points: {0}, streamer {1}, processing time: {2} sec'.format(report_info['expected_count'],
                                                                                      streamer.slug,
                                                                                      time.time() - start_time))

        return report_info['expected_count'], streamer_report


