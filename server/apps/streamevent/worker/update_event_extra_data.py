import json
import logging

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError

from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError
from apps.utils.data_helpers.manager import DataManager

logger = logging.getLogger(__name__)

WORKER_QUEUE_NAME = getattr(settings, 'SQS_WORKER_QUEUE_NAME')
RETRY_DELAY_SECONDS = 60 * 2  # in seconds


class UpdateEventExtraDataAction(Action):

    @classmethod
    def _arguments_ok(self, args):
        if 'extra_data' in args and 'uuid' in args:
            return True
        else:
            raise WorkerActionHardError('Missing fields in argument payload.\nReceived args: {}\nRequired args fields: uuid and extra_data'.format(args))

    def execute(self, arguments):
        super(UpdateEventExtraDataAction, self).execute(arguments)
        if UpdateEventExtraDataAction._arguments_ok(arguments):
            stream_event = None
            try:
                stream_event = DataManager.get('event', extras={'uuid': arguments['uuid']})
            except ObjectDoesNotExist as e:
                # For yet unkown reasons, it is possible for this action not to find the event record.
                # Until we better understand, simply try up to three times with a min delay between calls
                if 'attempts' in arguments and arguments['attempts'] >= 3:
                    raise WorkerActionHardError('Unable to find stream_event with uuid={}'.format(arguments['uuid']))
                else:
                    if 'attempts' not in arguments:
                        arguments['attempts'] = 0
                    arguments['attempts'] += 1
                    UpdateEventExtraDataAction.schedule(args=arguments, delay_seconds=RETRY_DELAY_SECONDS)
            except ValidationError:
                raise WorkerActionHardError("{} is not a valid uuid format".format(arguments['uuid']))
            try:
                extra_data = json.loads(arguments['extra_data'])  # expect arguments['extra_data'] to be a Json string
            except ValueError as e:  # arguments['extra_data'] can not be convert to Json
                raise WorkerActionHardError(str(e))

            if stream_event:
                if stream_event.extra_data:
                    stream_event.extra_data.update(extra_data)
                else:
                    stream_event.extra_data = extra_data
                DataManager.save('event', stream_event)
        else:
            raise WorkerActionHardError('Missing fields in argument payload. Error comes from UpdateEventExtraDataAction with arguments: {}'.format(arguments))

    @classmethod
    def schedule(cls, args=None, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        module_name = cls.__module__
        class_name = cls.__name__
        if UpdateEventExtraDataAction._arguments_ok(args):
            super(UpdateEventExtraDataAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
