import logging
import json
import time
import traceback
import time
import sys
from datetime import datetime
from django.utils import timezone

from django.conf import settings
from django.db.utils import InterfaceError, OperationalError, DatabaseError
from django import db
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.timezone_utils import str_utc
from apps.utils.dynamic_loading import str_to_class
from apps.utils.aws.sqs import get_sqs_messages, change_sqs_message_visibility
from .dynamodb import create_worker_log
from .exceptions import *
from .tracker import WorkerUUID
from .pid import ActionPID

logger = logging.getLogger(__name__)
WORKER_QUEUE_NAME = getattr(settings, 'SQS_WORKER_QUEUE_NAME')


class Worker(object):
    queue = None
    wait_time = None
    running = False
    id = None
    worker_task_log_obj = None

    def __init__(self, sqs_queue, wait_time):
        """
        :param sqs_queue: The sqs queue from which the worker reads tasks
        :param wait_time: sleeping time between 2 readings from sqs, in seconds
        """
        self.queue = sqs_queue
        self.wait_time = wait_time
        self.id = WorkerUUID.get_singleton()

    def set_wait_time(self, new_wait_time):
        self.wait_time = new_wait_time

    def notify_staff(self, error_txt, message=None, trace=None):
        msg = error_txt + '\n\n'
        if message:
            msg += 'SQS message ID {0}.\n-Message Body: {1}\n\n'.format(message.message_id, message.body)
        if trace:
            msg += trace

        if settings.PRODUCTION:
            sns_staff_notification(msg)

    def log_error(self, error_txt, message=None, trace=None):
        msg = error_txt + '\n\n'
        if message:
            msg += 'SQS message ID {0}.\n-Message Body: {1}\n\n'.format(message.message_id, message.body)
        if trace:
            msg += trace

        logger.error(msg)

    def get_action(self, task):
        """
        Based on module name and class name in sqs message.
        The action class must be an instance of apps.sqsworker.tasks.Action
        :param task: parsing from sqs message "arguments" field
        :return: Appropriate Action object
        """
        if 'module' in task and 'class' in task:
            logger.debug('Begin to work...Calling class {} from module {}'.format(task['class'], task['module']))
            try:
                action_class = str_to_class(task['module'], task['class'])
            except Exception as e:
                raise WorkerInternalError(e)
        else:
            raise WorkerInternalError('SQS message improperly configured : No "module" and "class" fields found')

        if 'arguments' in task and action_class:
            action = action_class()
        else:
            raise WorkerInternalError('SQS message improperly configured : No arguments field found')

        return action

    def call_action(self, action, task):
        """
        Calling Action based on module name and class name in sqs message.
        The action class must be an instance of apps.sqsworker.tasks.Action
        :param task: parsing from sqs message "arguments" field
        :return:
        """
        action.execute(arguments=task['arguments'])
        logger.info('Worker Task {0} completed. Execution Time = {1} secs'.format(action.get_name(),
                                                                                  action.get_execution_time()))

    def log_status(self, action, status):
        if self.worker_task_log_obj:
            self.worker_task_log_obj.execution_time = action.get_execution_time()
            self.worker_task_log_obj.status = status
            self.worker_task_log_obj.save()

    def delete_sqs_message(self, message):
        if message:
            ActionPID.delete(message.message_id)
            message.delete()

    def reschedule_sqs_message(self, message, delay):
        """This is done not by rescheude the task but simply
        by changing the message visibility to 60sec, whcih would
        result in SQS re queing the message in 60sec
        """
        if message:
            ActionPID.delete(message.message_id)
            change_sqs_message_visibility(message, delay)

    def _shutdown_procedure(self, err_msg, action, sqs_message):
        self.log_status(action, 'ShutDown-0')
        self.log_error(error_txt=str(err_msg), message=sqs_message)
        # First delete message to ensure it does not get re-queue
        self.delete_sqs_message(sqs_message)
        # Now enter a loop to three 30min sleeps, or abort after that
        count = 1
        while count <= 3:
            time.sleep(30 * 60)  # 30min
            msg = 'Alert {0}, ID={1} ==> Still waiting for shut down at {2}'.format(count, str(self.id),
                                                                                    timezone.now())
            self.log_error(error_txt=msg)
            self.log_status(action, 'ShutDown-{}'.format(count))
            count += 1

        msg = '{0}: ID={1} ==> Aborting shutdown after 90min at {2}'.format(count, str(self.id),
                                                                            timezone.now())
        self.log_error(error_txt=msg)
        self.log_status(action, 'ShutDown-AutoReboot')
        self.stop()

    def process_task(self, action, task, message=None):
        logger.info('Task message received: {0}!'.format(str(task)))
        try:
            action = self.get_action(task)
        except Exception as e:
            self.log_error(error_txt=str(e), message=message)
            self.delete_sqs_message(message)

        if action:
            self.id.increment_count()
            self.id.increment_action_count(task['class'])
            self.worker_task_log_obj = create_worker_log(uuid=str(self.id), task=task['class'], args=task['arguments'])
            try:
                self.call_action(action, task)
                self.log_status(action, 'done')
                self.delete_sqs_message(message)
            except  (InterfaceError, OperationalError, DatabaseError)  as e:
                # This is a database error. We want to requeue message and reboot
                self.reschedule_sqs_message(message, delay=60)
                self.log_status(action, 'WorkerDatabaseError')
                err = f'DB Error: Attempting to close all unused and obsoleted dbs: {e}'
                self.notify_staff(error_txt=err, message=message)
                for conn in db.connections.all():
                    conn.close_if_unusable_or_obsolete()
                # For now, exit anyway
                sys.exit()
            except WorkerInternalError as e:
                self.log_status(action, 'WorkerInternalError')
                formatted_lines = traceback.format_exc().splitlines()
                trace_back = "\n".join(formatted_lines)
                self.log_error(error_txt=str(e), message=message, trace=trace_back)
                self.delete_sqs_message(message)
                self.stop()
            except WorkerActionHardError as e:
                self.log_status(action, 'WorkerActionHardError')
                self.log_error(error_txt=str(e), message=message)
                self.delete_sqs_message(message)
            except WorkerActionSoftError as e:
                self.log_status(action, 'WorkerActionSoftError')
                self.notify_staff(error_txt=str(e), message=message)
                # Reprocess message in 5min
                self.reschedule_sqs_message(message, delay=300)
            except HaltAndCatchFire as e:
                self._shutdown_procedure(err_msg=e, action=action, sqs_message=message)
            except WorkerAbortSilently as e:
                # Just give a warning, email staff, but do not report as error
                self.log_status(action, 'WorkerAbortSilently')
                logger.warning(str(e))
                self.notify_staff(error_txt=str(e), message=message)
                self.delete_sqs_message(message)
            except Exception as e:
                self.log_status(action, 'WorkerInternalError')
                formatted_lines = traceback.format_exc().splitlines()
                trace_back = "\n".join(formatted_lines)
                self.log_error(error_txt=str(e), message=message, trace=trace_back)
                self.delete_sqs_message(message)
            finally:
                pass

    def run(self):
        """
        Run the worker with the given sqs queue and sleeping time
        :return:
        """
        logger.info('Running worker...')
        ts_now = str(timezone.now())
        self.id.start(ts_now)
        self.id.increment_action_count('WorkerStarted')
        sns_staff_notification("SQSWorker Started:\n\n - ID: {0}:{1}\n - Timestamp: {2}".format(settings.SERVER_TYPE, str(self.id), ts_now))
        create_worker_log(uuid=str(self.id), task='WorkerStarted', args="")

        self.running = True
        while self.running:
            try:
                messages = self.queue.receive_messages(MaxNumberOfMessages=1)
                if len(messages) > 0:
                    for message in messages:
                        action = None
                        task = json.loads(message.body)
                        if task:
                            self.process_task(action=action, task=task, message=message)
                else:
                    logger.debug('Nothing in SQS queue, worker goes to sleep at {}'.format(timezone.now()))
                    time.sleep(self.wait_time)
            except KeyboardInterrupt as e:
                self.stop()
                logger.info('Worker stopped.')

    def run_once_without_delete(self):
        """
        Run the worker with the given sqs queue and sleeping time
        :return:
        """
        logger.info('Running worker...')
        try:
            messages = get_sqs_messages(queue=self.queue, count=1)
            if len(messages) > 0:
                for message in messages:
                    action = None
                    task = json.loads(message.body)
                    if task:
                        self.process_task(action=action, task=task)

        except KeyboardInterrupt as e:
            self.stop()
            logger.info('Worker stopped.')

    def stop(self):
        self.running = False

