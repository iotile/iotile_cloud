import json
import logging

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.physicaldevice.models import Device
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError
from apps.streamfilter.cache_utils import cached_serialized_filter_for_slug
from apps.streamfilter.models import StreamFilter
from apps.streamfilter.process import FilterHelper
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.data_helpers.manager import DataManager

logger = logging.getLogger(__name__)

WORKER_QUEUE_NAME = getattr(settings, 'SQS_WORKER_QUEUE_NAME')


class ReprocessDeviceEventDataAction(Action):

    @classmethod
    def _arguments_ok(self, args):
        if 'device_slug' in args:
            return True
        else:
            raise WorkerActionHardError('Missing fields in argument payload.\nReceived args: {}\nRequired args fields: device_slug'.format(args))

    def execute(self, arguments):
        super(ReprocessDeviceEventDataAction, self).execute(arguments)
        if ReprocessDeviceEventDataAction._arguments_ok(arguments):

            try:
                device = Device.objects.get(slug=arguments['device_slug'])
            except Device.DoesNotExist:
                raise WorkerActionHardError("Device with slug {} not found !".format(arguments['device_slug']))

            project = device.project
            if project:
                filter_helper = FilterHelper(skip_dynamo_logs=True)
                qs = DataManager.filter_qs('event', device_slug=device.slug, project_slug=project.slug)
                msg = 'Reprocessing {0} events for {1}'.format(qs.count(), device.slug)
                logger.info(msg)
                for event in qs:
                    filter = cached_serialized_filter_for_slug(event.stream_slug)
                    if 'empty' not in filter:
                        filter_helper.process_filter(event, filter)
                sns_staff_notification(msg)

        else:
            raise WorkerActionHardError('Missing fields in argument payload. Error comes from UpdateEventExtraDataAction with arguments: {}'.format(arguments))

    @classmethod
    def schedule(cls, args=None, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME')):
        module_name = cls.__module__
        class_name = cls.__name__
        if ReprocessDeviceEventDataAction._arguments_ok(args):
            super(ReprocessDeviceEventDataAction, cls)._schedule(queue_name, module_name, class_name, args)
