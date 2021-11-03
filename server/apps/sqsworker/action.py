import logging
import json
import time

from django.conf import settings

from apps.utils.aws.sns import sns_staff_notification
from apps.utils.aws.sqs import get_queue_by_name

from .workerhelper import Worker
from .exceptions import WorkerActionHardError
from .pid import ActionPID

logger = logging.getLogger(__name__)


class Action(object):
    """
    Based action class that will be called by worker
    """
    sqs_arguments = None
    time0 = None

    def __init__(self):
        self.time0 = time.time()

    def execute(self, arguments):
        logger.info('Executing task...')
        self.sqs_arguments = arguments

    def get_name(self):
        return self.__class__.__name__

    def get_execution_time(self):
        if self.time0:
            time1 = time.time()
            return time1 - self.time0
        return -1

    @classmethod
    def _check_arguments(cls, args, required, optional, task_name):
        """
        Ensures all required arguments are given and that no other argument outside
        the required+optional set is given

        :param args: Raw arguments sent
        :param required: List of required arguments
        :param optional: List of optional arguments
        :param task_name: Task name used as label for error message
        :return: True if successful. Raises WorkerActionHardError if not
        """
        for key in required:
            if key not in args.keys():
                raise WorkerActionHardError('{} required for {}.'.format(key, task_name))
        for key in args.keys():
            if key not in required + optional:
                raise WorkerActionHardError('Illegal argument ({}) for {}'.format(key, task_name))
        return True

    @classmethod
    def _schedule(cls, queue_name, module_name, class_name, args, delay_seconds=None):
        """
        Schedule an action to the given queue
        :param queue_name: name of the SQS queue to send message to
        :param module_name: name of the package that contains class_name
        :param class_name: name of the action
        :param args: arguments that will be passed to specific action
        :param delay_seconds: Number of seconds that the action (message) will be delayed
        :return:
        """
        payload = {
            'module': module_name,
            'class': class_name,
            'arguments': args
        }
        if getattr(settings, 'USE_WORKER'):
            sqs_queue = get_queue_by_name(queue_name)
            if delay_seconds:
                response = sqs_queue.send_message(MessageBody=json.dumps(payload), DelaySeconds=delay_seconds)
            else:
                response = sqs_queue.send_message(MessageBody=json.dumps(payload))
            pid = ActionPID(response.get('MessageId'), class_name)
            pid.start()

            logger.info('{0}: Message sent (delay={2}) - ID: {1}'.format(class_name,
                                                                         response.get('MessageId'),
                                                                         delay_seconds if delay_seconds else 'Default'))
        else:
            worker = Worker(None, None)
            action = None
            worker.process_task(action=action, task=payload)
            pid = ActionPID('000000', class_name) # No need to start as it is in memory only

        return pid

    def handle_error(self, class_name, message):
        msg = "Error occurs when executing action {} : {}".format(class_name, message)
        logger.error(msg)
        sns_staff_notification(msg)

    def notify_admins(self, class_name, message):
        msg = "Notification from {0}\n{1}".format(class_name, message)
        logger.info(msg)
        sns_staff_notification(msg)