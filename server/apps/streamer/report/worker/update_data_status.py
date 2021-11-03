import logging

from django.conf import settings

from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerActionSoftError
from apps.utils.data_helpers.manager import DataManager

from .delay_checker import DelayChecker

logger = logging.getLogger(__name__)

STATUS_CHOICES = ['unk', 'cln', 'drt']


class UpdateDataStatusAction(Action):
    """
    This action update all data in a data block to the same status
    """
    device = None
    project = None

    def execute(self, arguments):
        super(UpdateDataStatusAction, self).execute(arguments)
        if 'device_slug' in arguments and 'start_id' in arguments and 'end_id' in arguments and 'project_id' in arguments and 'status' in arguments:
            try:
                self.device = Device.objects.get(slug=arguments['device_slug'])
            except Device.DoesNotExist:
                raise WorkerActionHardError("Device with slug {} not found !".format(arguments['device_slug']))
            try:
                self.project = Project.objects.get(id=arguments['project_id'])
            except Project.DoesNotExist:
                raise WorkerActionHardError("Project with id {} not found !".format(arguments['project_id']))
            if arguments['status'] not in STATUS_CHOICES:
                raise WorkerActionHardError("Invalid status")

            checker = DelayChecker(self, self.device, self.project, arguments['start_id'], arguments['end_id'])
            if checker.ready_to_process():
                logger.info("Data ready to process")
                count = DataManager.filter_qs('data', device_slug=self.device.slug, project_slug=self.project.slug, streamer_local_id__gte=arguments['start_id'],
                                              streamer_local_id__lte=arguments['end_id']).update(status=arguments['status'])
                logger.info("{} data point have been updated to status {}.".format(count, arguments['status']))
                checker.delete_count()
            else:
                if checker.continue_delay():
                    logger.info("Data not ready to process. Schedule to retry later")
                    UpdateDataStatusAction.schedule(args=arguments, delay_seconds=300)
        else:
            raise WorkerActionHardError('Missing fields in arguments payload. Error comes from task UpdateDataStatusAction, received args: {}'.format(arguments))

    @classmethod
    def schedule(cls, args, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        module_name = cls.__module__
        class_name = cls.__name__
        if 'device_slug' in args and 'start_id' in args and 'end_id' in args and 'status' in args and 'project_id' in args:
            super(UpdateDataStatusAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
        else:
            raise WorkerActionHardError('Missing fields in argument payload.\nReceived args: {}\nRequired args fields: device_slug, status, start_id, end_id, project_id'.format(args))
