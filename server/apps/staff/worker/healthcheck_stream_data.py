import logging

from django.conf import settings

from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerInternalError
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.data_helpers.manager import DataManager

logger = logging.getLogger(__name__)


class HealthCheckStreamDataAction(Action):

    def execute(self, arguments):
        super(HealthCheckStreamDataAction, self).execute(arguments)
        if 'ts' in arguments:
            ts = arguments['ts']
            future_data_count = DataManager.filter_qs('data', timestamp__gte=ts).count()
            if future_data_count > 0:
                msg = 'Found {0} Data Entries with timestamp in the future (ahead of {1})'.format(future_data_count, ts)
                msg += '\n\n{0}/api/v1/data/?filter=future&staff=1'.format(getattr(settings, 'DOMAIN_BASE_URL'))
                logger.warning(msg)
                sns_staff_notification(msg)
            else:
                logger.info('All StreamData looks good. No timestamps in the future')

    @classmethod
    def schedule(cls, args, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        module_name = cls.__module__
        class_name = cls.__name__
        if 'ts' in args:
            super(HealthCheckStreamDataAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
        else:
            raise WorkerInternalError('Missing fields in argument payload.\nReceived args: {}\nRequired args fields: ts (now)'.format(
                    args))
