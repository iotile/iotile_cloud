import datetime
import logging
from pprint import pprint

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError
from apps.stream.models import StreamId
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.data_helpers.manager import DataManager
from apps.utils.timezone_utils import formatted_ts

user_model = get_user_model()
logger = logging.getLogger(__name__)


class SyncUpE2DataAction(Action):
    _stream_slug = None
    _stream = None
    _seq_ids = []
    _attempt_count = 0

    @classmethod
    def _arguments_ok(self, args):
        if 'stream_slug' not in args.keys():
            raise WorkerActionHardError('stream_slug required for SyncUpE2DataAction.')
        for key in args.keys():
            if key not in ['stream_slug', 'seq_ids', 'attempt_count']:
                raise WorkerActionHardError('Illegal argument ({}) for SyncUpE2DataAction'.format(key))
        return True

    def _syncup_e2_data(self):
        """
        For every stream of type E2 (Unstructured Events with Data Pointer),
        Find all associated data, and use it to update the timestamps.
        It is possible that data has not yet made it to the database,
        If so, schedule a delayed task to retry
        """
        if self._stream.enabled and self._stream.data_type == 'E2':
            if self._seq_ids:
                data_qs = DataManager.filter_qs(
                    'data', stream_slug=self._stream_slug, extras={'int_value__in': self._seq_ids},
                )
                event_qs = DataManager.filter_qs(
                    'event', streamer_local_id__in=self._seq_ids, stream_slug=self._stream_slug
                )
                if data_qs.count() and event_qs.count():
                    event_map = {}
                    for event in event_qs:
                        seq_id = event.incremental_id
                        event_map[seq_id] = event

                    logger.info('Processing {} events'.format(len(event_map.keys())))

                    with transaction.atomic():
                        for data in data_qs:
                            if data.int_value in event_map:
                                # Get event from event map, but also remove so we don't re-process
                                event = event_map.pop(data.int_value)
                                if event.timestamp != None:
                                    event.timestamp = parse_datetime(formatted_ts(data.timestamp))
                                    event.device_timestamp = data.device_timestamp
                                    DataManager.save('event', event)

                    # Update array with any left off ids, in case we only got partial list
                    self._seq_ids = event_map.keys()
                else:
                    msg = 'SyncUpE2DataAction failed to find either events ({}) or data ({}) for {}'. format(
                        event_qs.count(), data_qs.count(), self._stream.slug
                    )
                    if not sns_staff_notification(msg):
                        logger.warning(msg)

                if self._seq_ids:
                    attempts_left = self._attempt_count - 1
                    msg = 'Still have {} unprocess ids for {}. Attempt={}'.format(
                        len(self._seq_ids), self._stream_slug, attempts_left
                    )
                    logger.warning(msg)
                    sns_staff_notification(msg)
                    if attempts_left:
                        args = {
                            'stream_slug': self._stream_slug,
                            'seq_ids': list(self._seq_ids),
                            'attempt_count': attempts_left
                        }
                        SyncUpE2DataAction.schedule(args=args, delay_seconds=900)
                    else:
                        raise WorkerActionHardError('Too many attempts to process E2 events for {}: {}'.format(
                            self._stream_slug, str(self._seq_ids)
                        ))
            else:
                raise WorkerActionHardError('SyncUpE2DataAction._syncup_e2_data cannot be called with no seq_ids')
        else:
            msg = 'SyncUpE2DataAction called with either disabled stream or wrong data type. stream={}, enabled={}, data_type={}'.format(
                self._stream.slug, self._stream.enabled, self._stream.data_type
            )
            logger.warning(msg)
            sns_staff_notification(msg)

    def execute(self, arguments):
        super(SyncUpE2DataAction, self).execute(arguments)
        if SyncUpE2DataAction._arguments_ok(arguments):
            try:
                self._stream_slug = arguments['stream_slug']
                try:
                    self._stream = StreamId.objects.get(slug=arguments['stream_slug'])
                except StreamId.DoesNotExist:
                    raise WorkerActionHardError('Stream not found: {}'.format(arguments['stream_slug']))

                self._attempt_count = arguments['attempt_count']
                self._seq_ids = arguments['seq_ids']

                if not isinstance(self._seq_ids, list):
                    raise WorkerActionHardError("Expected seq_ids to be a list. Got: {}".format(arguments['seq_ids']))
                if len(self._seq_ids) == 0:
                    raise WorkerActionHardError("seq_ids is empty. Got: {}".format(str(arguments)))

                if self._attempt_count:
                    self._syncup_e2_data()
            except StreamId.DoesNotExist:
                raise WorkerActionHardError("Stream with slug {} not found !".format(arguments['stream_slug']))

    @classmethod
    def schedule(cls, args=None, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        module_name = cls.__module__
        class_name = cls.__name__
        if SyncUpE2DataAction._arguments_ok(args):
            Action._schedule(queue_name, module_name, class_name, args, delay_seconds)
