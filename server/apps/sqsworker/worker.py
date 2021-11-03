import logging
import datetime
from django.conf import settings
from apps.sqsworker.action import Action
from apps.utils.aws.sns import sns_staff_notification
from django.utils import timezone
from django.core.cache import cache
from django.utils.dateparse import parse_datetime

from .exceptions import WorkerActionHardError, HaltAndCatchFire
from .tracker import WorkerUUID
from .dynamodb import DynamoWorkerLogModel
from .common import ACTION_LIST
from .models import WorkerStatistics
logger = logging.getLogger(__name__)

WORKER_LAST_PIN_DT = 'sqs-worker-last-ping'
WORKER_QUEUE_NAME = getattr(settings, 'SQS_WORKER_QUEUE_NAME')


class PingAction(Action):
    def execute(self, arguments):
        super(PingAction, self).execute(arguments)
        if 'message' in arguments:
            msg = arguments['message']
            logger.info("PingAction on worker return active status with message: {}".format(msg))
            sns_staff_notification("PingAction on {0}:\n {1}".format(settings.SERVER_TYPE , msg))

            if cache:
                key = WORKER_LAST_PIN_DT
                cache.set(key, timezone.now(), timeout=None)

        else:
            raise WorkerActionHardError('Message not found in arguments. Error comes from Ping Action with arguments: {}'.format(arguments))

    @classmethod
    def schedule(cls, args=None, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME')):
        module_name = cls.__module__
        class_name = cls.__name__
        if args:
            if 'message' not in args:
                raise WorkerActionHardError('Missing fields in argument payload.\nReceived args: {}\nRequired args : message'.format(args))
        else:
            args = {
                'message': 'hello'
            }
        super(PingAction, cls)._schedule(queue_name, module_name, class_name, args)


class WorkerHealthCheckAction(Action):
    def execute(self, arguments):
        super(WorkerHealthCheckAction, self).execute(arguments)
        if 'message' in arguments:
            msg = arguments['message']
            logger.info('WorkerHealthCheckAction  on {0}:\n {1}'.format(settings.SERVER_TYPE , msg))

            if cache:
                key = WORKER_LAST_PIN_DT
                last_pin_dt = cache.get(key)
                logger.info('Last worker pin on {}'.format(last_pin_dt))
                cache.set(key, timezone.now(), timeout=None)

        else:
            raise WorkerActionHardError('Message not found in arguments. Error comes from WorkerHealthCheckAction with arguments: {}'.format(arguments))

    @classmethod
    def schedule(cls, args=None, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME')):
        module_name = cls.__module__
        class_name = cls.__name__
        if args:
            if 'message' not in args:
                raise WorkerActionHardError('Missing fields in argument payload.\nReceived args: {}\nRequired args : message'.format(args))
        else:
            args = {
                'message': 'hello'
            }
        super(WorkerHealthCheckAction, cls)._schedule(queue_name, module_name, class_name, args)


class WorkerShutDownAction(Action):

    def execute(self, arguments):
        super(WorkerShutDownAction, self).execute(arguments)
        if 'timestamp' in arguments:
            ts = arguments['timestamp']
            worker_uuid = WorkerUUID.get_singleton()
            msg = 'Ready for shutting down\n - Server: {0}\n - ID: {1}\n - Timestamp: {2}'.format(settings.SERVER_TYPE,
                                                                                                  str(worker_uuid), ts)
            raise HaltAndCatchFire(msg)
        else:
            raise WorkerActionHardError('Timestamp not found in arguments. Error comes from WorkerShutDownAction with arguments: {}'.format(arguments))

    @classmethod
    def schedule(cls, args=None, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME')):
        module_name = cls.__module__
        class_name = cls.__name__
        args = {
            'timestamp': str(timezone.now())
        }
        super(WorkerShutDownAction, cls)._schedule(queue_name, module_name, class_name, args)


class WorkerCollectStatsAction(Action):

    def _create_stats_for_task(self, task_name, timestamp, span):
        span_seconds = {
            'd': 24*60*60,
            'w': 7*24*60*60,
            'm': 30*24*60*60
        }
        if span in span_seconds:
            start_ts = timestamp - datetime.timedelta(seconds=span_seconds[span])
            total_count = 0
            error_count = 0
            total_time = 0
            try:
                for item in DynamoWorkerLogModel.task_index.query(task_name, timestamp > start_ts):
                    total_count += 1
                    if item.status != "done" and item.status != "executing":
                        error_count += 1
                    if item.execution_time:
                        total_time += item.execution_time
            except Exception:
                pass
            stat = WorkerStatistics.objects.create(timestamp=timestamp,
                                                   span=span,
                                                   task_name=task_name,
                                                   total_count=total_count,
                                                   error_count=error_count,
                                                   total_execution_time=total_time)
            logger.info("Statistics created: {}".format(str(stat)))
        else:
            raise WorkerActionHardError('Invalid argument span = {}. Expected d, w or m'.format(span))

    def execute(self, arguments):
        super(WorkerCollectStatsAction, self).execute(arguments)
        if 'ts' in arguments and 'span' in arguments:
            for task_name in ACTION_LIST:
                self._create_stats_for_task(task_name=task_name, timestamp=parse_datetime(arguments['ts']), span=arguments['span'])
            logger.info("Finish creating statistics for worker's task at ts {}, span : {}".format(arguments['ts'], arguments['span']))
        else:
            raise WorkerActionHardError('Missing fields in argument payload. Error comes from WorkerCollectStatsAction with arguments: {}'.format(arguments))

    @classmethod
    def schedule(cls, args=None, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME')):
        module_name = cls.__module__
        class_name = cls.__name__
        if 'ts' in args and 'span' in args:
            super(WorkerCollectStatsAction, cls)._schedule(queue_name, module_name, class_name, args)
        else:
            raise WorkerActionHardError('Missing fields in argument payload.\nReceived args: {}\nRequired args :start, end'.format(args))

