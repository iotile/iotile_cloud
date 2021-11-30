import datetime
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.physicaldevice.models import Device
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.data_helpers.manager import DataManager
from apps.utils.timezone_utils import convert_to_utc, str_to_dt_utc

user_model = get_user_model()
logger = logging.getLogger(__name__)


class AdjustTimestampReverseV2Action(Action):
    """
    This task can be used to update a range of ids to a new timestamp based
    on the last entry in the start-end range.
    This action is useful for devices that on their first upload, multiple reboots are found.
    Assumes the last item in the range is always correct (from the original sent_timestamp).

    It is a good idea to use the first_original_id and Last_original_id from the streamer report upload.
    """
    _data_entries = []
    _event_entries = []
    _start = None
    _end = None
    _base_ts = None
    _type = None
    _use_firehose = False

    @classmethod
    def _arguments_ok(self, args):
        """
        - "start" and "end" are the seqids for the data ranges (inclusive)
        - "device_slug" is the target device
        - "type" should be either "data" or "event"
        - "use_firehose" is an optional parameter to use firehose to create modified entries, and delete old
        """
        return Action._check_arguments(
            args=args, task_name='AdjustTimestampReverseV2Action',
            required=['device_slug', 'start', 'end', 'type'], optional=['use_firehose'],
        )

    def _get_data_entries(self, model):
        """
        Get StreamData filter from start to end for given device.
        Sort from last streamer id to first
        """
        qs = DataManager.filter_qs(
            model,
            device_slug=self._device.slug,
            streamer_local_id__gte=self._start,
            streamer_local_id__lte=self._end,
        ).order_by('-streamer_local_id')

        return qs

    def _adjust_data_timestamps(self, entries):
        """
        Iterate entries from back and adjust timestampt as it goes
        """
        next_item = None
        for item in entries:
            if not item.has_utc_synchronized_device_timestamp:
                if next_item:
                    delta = next_item.device_timestamp - item.device_timestamp
                    if delta < 0:
                        delta = next_item.device_timestamp

                    new_timestamp = convert_to_utc(next_item.timestamp) - datetime.timedelta(seconds=delta)

                    if item.timestamp != new_timestamp:
                        item.timestamp = new_timestamp
                        item.status = 'cln'
                        item.dirty_ts = False
            next_item = item

    def _commit_changes(self, model, entries, use_firehose=False):
        if use_firehose:
            DataManager.send_to_firehose('data', entries)
        else:
            with transaction.atomic():
                for item in entries:
                    DataManager.save(model, item)

    def process_data(self):
        start_time = timezone.now()

        self._data_entries = []
        self._event_entries = []
        count = 0

        # Adjust StreamData if needed
        if self._type == 'data':
            self._data_entries = self._get_data_entries('data')
            count = self._data_entries.count()
            self._adjust_data_timestamps(self._data_entries)
            self._commit_changes(model='data', entries=self._data_entries, use_firehose=self._use_firehose)
            if self._use_firehose:
                # When using firehose, we are speeding up by creating new data
                # and deleting old, instead of having to modify each entry one by one
                self._data_entries.delete()

        # Adjust StreamEventData if needed
        if self._type == 'event':
            self._event_entries = self._get_data_entries('event')
            count = self._event_entries.count()
            self._adjust_data_timestamps(self._event_entries)
            # Events are currently stored on a main db, so no firehose is available
            self._commit_changes(model='event', entries=self._event_entries, use_firehose=False)

        msg = 'Time to move {0} {1} record(s) for {2}: {3} sec'.format(count, self._type, self._device.slug,
                                                                       timezone.now() - start_time)

        sns_staff_notification(msg)

        logger.info(msg)

        return count

    def execute(self, arguments):
        self.sqs_arguments = arguments
        if AdjustTimestampReverseV2Action._arguments_ok(arguments):

            device_slug = arguments['device_slug']
            self._start = int(arguments['start'])
            self._end = int(arguments['end'])
            self._type = arguments['type']
            self._use_firehose = arguments.get('use_firehose', False)

            try:
                self._device = Device.objects.get(slug=device_slug)
            except Device.DoesNotExist:
                raise WorkerActionHardError('Device not Found {}'.format(device_slug))

            self.process_data()

    @classmethod
    def schedule(cls, args=None, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        module_name = cls.__module__
        class_name = cls.__name__
        if AdjustTimestampReverseV2Action._arguments_ok(args):
            super(AdjustTimestampReverseV2Action, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
