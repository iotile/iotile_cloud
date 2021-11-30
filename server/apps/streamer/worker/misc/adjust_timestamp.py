import datetime
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.datablock.models import DataBlock
from apps.emailutil.tasks import Email
from apps.physicaldevice.models import Device
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerActionSoftError
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.data_helpers.manager import DataManager
from apps.utils.timezone_utils import convert_to_utc, str_to_dt_utc

from ..common.base_action import get_utc_read_data_timestamp

user_model = get_user_model()
logger = logging.getLogger(__name__)


class AdjustTimestampAction(Action):
    """
    This task can be used to update a range of ids to a new timestamp based
    on a given base_ts..
    For every data point, the new timestamp will be base_ts+device_timestamp
    """
    _data_entries = []
    _event_entries = []
    _start = None
    _end = None
    _base_ts = None
    _type = None
    _user = None
    _object = None

    @classmethod
    def _arguments_ok(self, args):
        """
        - "base_ts" is the absolute (Datetime) base timestamp to use for adjustment
        - "start" and "end" are the seqids for the data ranges (inclusive)
        - "device_slug" is the target device
        - "type" should be either "data" or "event"
        """
        return Action._check_arguments(
            args=args, task_name='AdjustTimestampV2Action',
            required=['base_ts', 'device_slug', 'start', 'end', 'type'], optional=['user'],
        )

    def _get_data_entries(self, model):
        """
        Get StreamData filter from start to end for given device
        """
        qs = DataManager.filter_qs(
            model,
            device_slug=self._object.slug,
            streamer_local_id__gte=self._start,
            streamer_local_id__lte=self._end,
        ).order_by('streamer_local_id')

        return qs

    def _adjust_data_timestamps(self, model, entries):
        """
        Just move all data based on the given _base_ts
        """
        count = 0
        with transaction.atomic():
            previous_item = None
            for item in entries:
                if not item.has_utc_synchronized_device_timestamp:
                    if previous_item:
                        delta = item.device_timestamp - previous_item.device_timestamp
                        if delta < 0:
                            delta = item.device_timestamp
                        new_timestamp = convert_to_utc(previous_item.timestamp + datetime.timedelta(seconds=delta))
                    else:
                        new_timestamp = convert_to_utc(self._base_ts + datetime.timedelta(seconds=item.device_timestamp))
                    if item.timestamp != new_timestamp:
                        item.timestamp = new_timestamp
                        item.status = 'cln'
                        item.dirty_ts = False
                        DataManager.save(model, item)
                        count += 1
                previous_item = item
        return count

    def process_data(self):
        start_time = timezone.now()

        self._data_entries = []
        self._event_entries = []
        original_count = actual_count = 0

        # Adjust StreamData if needed
        if self._type == 'data':
            self._data_entries = self._get_data_entries('data')
            original_count = self._data_entries.count()
            actual_count = self._adjust_data_timestamps('data', self._data_entries)

        # Adjust StreamEventData if needed
        if self._type == 'event':
            self._event_entries = self._get_data_entries('event')
            original_count = self._event_entries.count()
            actual_count = self._adjust_data_timestamps('event', self._event_entries)

        msg = 'Time to move {0} {1} record(s) for {2}: {3} sec\n Actual records moved: {4}'.format(
            original_count, self._type, self._object.slug, timezone.now() - start_time, actual_count
        )
        logger.info(msg)
        if self._user is None:
            sns_staff_notification(msg)
        else:
            self._notify_user(msg)

        return actual_count

    def _notify_user(self, msg):
        email = Email()
        ctx = {
            'device_slug': self._object.slug,
            'device_label': self._object.label,
            'msg': msg,
            'url': settings.DOMAIN_BASE_URL + self._object.get_absolute_url(),
        }
        subject = 'IOTile Cloud Notification: Device Data Fixed ({})'.format(self._object.slug)
        emails = [self._user.email, ]
        try:
            email.send_email(label='streamer/adjust_confirmation', subject=subject, ctx=ctx, emails=emails)
        except Exception as e:
            logger.warning(str(e))
            # If the email failed, we want to try again, so we don't delete the SQS message
            raise WorkerActionSoftError(
                "Error when sending email. This task will be executed again after the default visibility timeout")

    def execute(self, arguments):
        self.sqs_arguments = arguments
        if AdjustTimestampAction._arguments_ok(arguments):

            device_slug = arguments['device_slug']
            self._start = int(arguments['start'])
            self._end = int(arguments['end'])
            self._type = arguments['type']
            self._base_ts = str_to_dt_utc(arguments['base_ts'])

            if 'user' in arguments:
                user_slug = arguments['user']
                try:
                    self._user = user_model.objects.get(slug=user_slug)
                except user_model.DoesNotExist:
                    logger.error('User does not exist: {}'.format(user_slug))
                    raise WorkerActionHardError('User not found: {}'.format(user_slug))

            try:
                self._object = Device.objects.get(slug=device_slug)
            except Device.DoesNotExist:
                try:
                    self._object = DataBlock.objects.get(slug=device_slug)
                except DataBlock.DoesNotExist:
                    raise WorkerActionHardError('Device or Datablock not Found {}'.format(device_slug))

            self.process_data()

    @classmethod
    def schedule(cls, args=None, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        module_name = cls.__module__
        class_name = cls.__name__
        if AdjustTimestampAction._arguments_ok(args):
            super(AdjustTimestampAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
