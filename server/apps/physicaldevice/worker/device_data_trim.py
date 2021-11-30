import logging

import pytz

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from apps.emailutil.tasks import Email
from apps.physicaldevice.models import Device
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerActionSoftError
from apps.stream.models import StreamId
from apps.streamnote.models import StreamNote
from apps.utils.data_helpers.manager import DataManager
from apps.utils.iotile.variable import DATA_TRIM_EXCLUSION_LIST
from apps.utils.timezone_utils import convert_to_utc, str_to_dt_utc

logger = logging.getLogger(__name__)
user_model = get_user_model()


def get_streams_to_trim(device):
    """
    Get query set for valid streams to trim
    For example, we want to keep the trip start and trip ended around even after the trim

    :param device: Device object
    :return: queryset
    """
    assert device
    q = Q(lid__in=DATA_TRIM_EXCLUSION_LIST) | Q(app_only=True)
    var_exclude_qs = device.project.variables.filter(q)
    stream_qs = device.streamids.filter(block__isnull=True, device__isnull=False, project=device.project)
    stream_qs = stream_qs.exclude(variable__in=var_exclude_qs)

    return stream_qs


class DeviceDataTrimAction(Action):
    """
    This action will trip data by removing all data before the <start> datetime and after the <end> datetime.
    Data for streams in DATA_TRIM_EXCLUSION_LIST are not deleted
    Actions:
    - Deleting all StreamData points outside boundaries
    - Deleting all StreamEventData points outside boundaries
    - Adds a StreamNote documenting action
    """
    _device = None
    _user = None
    _start = None
    _end = None
    _logs = []
    _oldest = None
    _newest = None

    @classmethod
    def _arguments_ok(self, args):
        if 'device_slug' not in args.keys() or 'username' not in args.keys():
            raise WorkerActionHardError('device_slug and username are required for DeviceDataTrimAction.')
        for key in args.keys():
            if key not in ['username', 'device_slug', 'start', 'end']:
                raise WorkerActionHardError('Illegal argument ({}) for DeviceDataTrimAction'.format(key))
        return True

    def _trim_data(self):
        logger.info('Trimming DataStreams and DataEventStreams for {}'.format(self._device))
        assert(self._device)
        # We don't want to delete system information that may be useful regardless of trimming,
        # For example, we want to keep the trip start and trip ended around even after the trim
        stream_qs = get_streams_to_trim(self._device)
        stream_slugs = [s.slug for s in stream_qs]

        if self._start:
            data_qs = DataManager.filter_qs('data', stream_slug__in=stream_slugs, device_slug=self._device.slug)
            event_qs = DataManager.filter_qs('event', stream_slug__in=stream_slugs, device_slug=self._device.slug)

            logger.info('First Data: {}'.format(data_qs.order_by('timestamp').first()))
            data0_qs = data_qs.filter(timestamp__lt=self._start)
            first_data = None
            if data0_qs.exists():
                msg = '{0} data row(s) before {1} deleted'.format(data0_qs.count(), self._start)
                logger.info(msg)
                self._logs.append(msg)
                first_data = data0_qs.first()
                self._oldest = convert_to_utc(first_data.timestamp)
                data0_qs.delete()

            logger.info('First Event: {}'.format(event_qs.order_by('timestamp').first()))
            event0_qs = event_qs.filter(timestamp__lt=self._start)
            if event0_qs.exists():
                msg = '{0} event row(s) before {1} deleted'.format(event0_qs.count(), self._start)
                logger.info(msg)
                self._logs.append(msg)
                older_event = event0_qs.first()
                if older_event and (not first_data or (older_event.timestamp < self._oldest)):
                    self._oldest = older_event
                event0_qs.delete()

        if self._end:
            data_qs = DataManager.filter_qs('data', stream_slug__in=stream_slugs, device_slug=self._device.slug)
            event_qs = DataManager.filter_qs('event', stream_slug__in=stream_slugs, device_slug=self._device.slug)

            logger.info('Last Data: {}'.format(data_qs.order_by('timestamp').last()))
            data1_qs = data_qs.filter(timestamp__gt=self._end)
            last_data = None
            if data1_qs.exists():
                msg = '{0} data row(s) after {1} deleted'.format(data1_qs.count(), self._end)
                logger.info(msg)
                self._logs.append(msg)
                last_data = data1_qs.last()
                self._newest = convert_to_utc(last_data.timestamp) if last_data else None
                data1_qs.delete()

            logger.info('Last Event: {}'.format(event_qs.order_by('timestamp').last()))
            event1_qs = event_qs.filter(timestamp__gt=self._end)
            if event1_qs.exists():
                msg = '{0} event row(s) after {1} deleted'.format(event1_qs.count(), self._end)
                logger.info(msg)
                self._logs.append(msg)
                newest_event = event1_qs.last()
                if newest_event and (not last_data or (newest_event.timestamp > self._newest)):
                    self._newest = newest_event.timestamp
                event1_qs.delete()

    def _notify_user(self):
        email = Email()
        ctx = {
            'device_slug': self._device.slug,
            'device_label': self._device.label,
            'start': self._start,
            'end': self._end,
            'oldest': self._oldest,
            'newest': self._newest,
            'logs': self._logs,
            'url': self._device.get_webapp_url(),
        }
        subject = 'IOTile Cloud Notification'
        # Only send notification to user that initiated task
        emails = [self._user.email]
        try:
            email.send_email(label='device/trim_confirmation', subject=subject, ctx=ctx, emails=emails)
        except Exception as e:
            logger.warning(str(e))
            # If the email failed, we want to try again, so we don't delete the SQS message
            raise WorkerActionSoftError(
                "Error when sending email. This task will be executed again after the default visibility timeout")

    def _log_stream_note(self):
        msg = 'Device data trim task executed ('
        if self._start:
            msg += ' start: {}'.format(self._start)
        if self._end:
            msg += ' end: {}'.format(self._end)
        msg += ' )'
        for log in self._logs:
            msg += '\n- {}'.format(log)

        StreamNote.objects.create(target_slug=self._device.slug,
                                  timestamp=timezone.now(),
                                  note=msg,
                                  created_by=self._user)

    def execute(self, arguments):
        super(DeviceDataTrimAction, self).execute(arguments)
        if DeviceDataTrimAction._arguments_ok(arguments):
            self._logs = []

            try:
                self._device = Device.objects.get(slug=arguments['device_slug'])
            except Device.DoesNotExist:
                raise WorkerActionHardError("Device with slug {} not found !".format(arguments['device_slug']))

            try:
                self._user = user_model.objects.get(username=arguments['username'])
            except user_model.DoesNotExist:
                raise WorkerActionHardError("User @{} not found !".format(arguments['username']))

            if 'start' in arguments and arguments['start']:
                self._start = convert_to_utc(str_to_dt_utc(arguments['start']))
                logger.info('Worker Trim Start: {}'.format(self._start))
            if 'end' in arguments and arguments['end']:
                self._end = convert_to_utc(str_to_dt_utc(arguments['end']))
                logger.info('Worker Trim End: {}'.format(self._end))

            # 1. Delete StreamData and StreamEventData outside start/end boundary
            self._trim_data()

            if len(self._logs) == 0:
                self._logs.append('No data deleted')

            # 2. Notify User
            self._notify_user()

            # 3. Log
            self._log_stream_note()

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
        if DeviceDataTrimAction._arguments_ok(args):
            super(DeviceDataTrimAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
