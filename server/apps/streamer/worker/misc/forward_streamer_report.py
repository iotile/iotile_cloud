import json
import logging
import requests
from urllib import parse

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from iotile_cloud.api.connection import Api
from iotile_cloud.api.exceptions import HttpClientError, HttpServerError

from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerActionSoftError
from apps.streamer.models import StreamerReport
from apps.configattribute.models import ConfigAttribute
from apps.utils.aws.s3 import download_file_from_s3

logger = logging.getLogger(__name__)


def _get_forwarding_cloud_info(org_slug):
    """
    Check if there are any Config Attributes for the given Org with
    forwarding details.
    Cached result to optimize repeated access (24hrs)

    Args:
        org: Organization Object

    Returns:
        Object with forwarding info
        {
            "enabled": True,
            "api_url": "https://arch.archfx.io",
            "api_key": "abc-123",
        }
    """
    config_name = ':classic:streamer:forwarder:config'
    config_attr = {}
    cache_key = '::'.join([config_name, org_slug])
    if cache:
        config_attr = cache.get(cache_key)
    if config_attr:
        # print(f'Retuning from cache: {config_attr}')
        return config_attr
    else:
        # Build proper Org Config Attribute target slug format. e.g. '^arch'
        target_slug = f'^{org_slug}'
        config_attr = ConfigAttribute.objects.get_attribute_by_slug(name=config_name, target_slug=target_slug)
        if config_attr:
            cache.set(cache_key, config_attr.data, timeout=86400)
            # print('Returned not cached: {}'.format(config_attr.data))
            return config_attr.data
        default_config_data = {
            'enabled': False
        }
        cache.set(cache_key, default_config_data, timeout=86400)
        return default_config_data


def _upload_streamer_report_to_cloud(api, fp, sent_ts):
    """
    Given a streamer report file pointer and sent timestamp,
    Upload file to a secondary Cloud using the initialized Api

    Args:
        api: iotile_cloud.api.connection Api object
        fp: opened file pointer for Streamer Report
        sent_ts: ISO Datetime string reprenting ts the report was sent

    Returns:
        None
    """
    try:
        api.streamer().report.upload_fp(fp=fp, timestamp=sent_ts)
    except HttpClientError as e:
        logger.warning(f'--> Unable to upload report. ClientError: {e}')
        print(str(e))
    except HttpServerError as e:
        logger.warning(f'--> Unable to upload report. ServerError: {e}')
        print(str(e))


class ForwardStreamerReportAction(Action):
    """
    This task forwards a given streamer report to another
    cloud (ArchFx Cloud) for it to process it in parallel
    with IOTile Cloud
    """
    _config = {}

    @classmethod
    def _arguments_ok(self, args):
        """
        Check Task arguments. Expected:
        - "org": Organization Slug (passed to make it simple)
        - "report": Streamer Report ID
        - "ext": Streamer Report file extension (e.g. '.bin')

        Args:
            args: Dict with task arguments to check
        """
        return Action._check_arguments(
            args=args, task_name='ForwardStreamerReportAction',
            required=['org', 'report', 'ext', ], optional=[],
        )

    def _forward_report(self, fp, streamer_report):
        """
        Upload file pointer representing streamer report to
        the appropriate ArchFx Cloud using the API Key.
        URL and Key is assumed to be in previously found
        Config Attribute for this Organization

        Args:
            fp: File Pointer to Streamer Report
            streamer_report: Streamer Report Instance
        """
        assert self._config
        domain = self._config.get('api_url')
        api_key = self._config.get('api_key')
        c = Api(domain)
        c.set_token(api_key, token_type='Api-Key')

        sent_ts = streamer_report.sent_timestamp
        ts = sent_ts.isoformat()

        logger.info(f'Uploading Streamer Report {streamer_report.id} @ {ts}')
        _upload_streamer_report_to_cloud(api=c, fp=fp, sent_ts=ts)

    def execute(self, arguments):
        """
        Execute this task by finding the given Streamer Report,
        downloading it from S3, and uploading to the new Cloud.
        New Cloud URL and API Key stored on Config Attribute for
        given Organization.

        Args:
            arguments: Dictionary with task arguments
        """
        self.sqs_arguments = arguments
        if ForwardStreamerReportAction._arguments_ok(arguments):

            org_slug = arguments['org']
            self._config = _get_forwarding_cloud_info(org_slug)
            if not self._config:
                return
            if not self._config.get('enabled', False):
                return

            report_id = arguments['report']
            ext = arguments['ext']

            try:
                streamer_report = StreamerReport.objects.get(pk=report_id)
            except StreamerReport.DoesNotExist:
                logger.warning(
                    'Report not found: {0}'.format(report_id)
                )
                return

            bucket, key = streamer_report.get_dropbox_s3_bucket_and_key(ext)

            self._decoded_key = parse.unquote(key)
            try:
                fp = download_file_from_s3(bucket, self._decoded_key)
                # fp.name = os.path.basename(self._decoded_key)
            except Exception as e:
                # No crashing even if we cannot find report
                logger.warning(
                    'Incorrect report in bucket {1}, key {2}: {0}'.format(str(e), bucket, key)
                )
                print('Incorrect report in bucket {1}, key {2}: {0}'.format(str(e), bucket, key))
                return

            # Upload Report on secondary Cloud
            # Need to flush and reset fp
            fp.flush()
            fp.seek(0)
            self._forward_report(fp, streamer_report)
            fp.close()


    @classmethod
    def schedule(cls, args=None, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        module_name = cls.__module__
        class_name = cls.__name__
        if ForwardStreamerReportAction._arguments_ok(args):
            org_slug = args['org']
            info = _get_forwarding_cloud_info(org_slug)
            if info and info.get('enabled', False):
                # Only schedule worker if we find a configuration and
                # the featured is enabled
                super(ForwardStreamerReportAction, cls)._schedule(
                    queue_name, module_name, class_name, args, delay_seconds
                )
