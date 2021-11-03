import logging

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.emailutil.tasks import Email
from apps.physicaldevice.models import Device
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerActionSoftError
from ..claim_utils import device_unclaim

logger = logging.getLogger(__name__)


class DeviceUnClaimAction(Action):
    """
    This action will unclaim a device
    """
    _user = None
    _device = None
    _move_data = False
    _src_project = None
    _dst_project = None

    @classmethod
    def _arguments_ok(cls, args):
        return Action._check_arguments(
            args=args, task_name='DeviceUnClaimAction',
            required=[
                'device',
                'clean_streams'
            ],
            optional=[
                'label'
            ]
        )

    def execute(self, arguments):
        super().execute(arguments)
        if DeviceUnClaimAction._arguments_ok(arguments):
            device_slug = arguments['device']
            clean_streams = arguments.get('clean_streams', False)
            label = arguments.get('label', f'Device {device_slug}')

            try:
                device = Device.objects.get(slug=device_slug)
            except Device.DoesNotExist:
                raise WorkerActionHardError("Device with slug {} not found !".format(device_slug))
            
            logger.info('Unclaiming device {0}; should clean streams? {1}'.format(device, clean_streams))

            msg = device_unclaim(device=device, label=label, clean_streams=clean_streams)
            logger.info(msg)

    @classmethod
    def schedule(cls, args, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        """
        schedule function should always have at least args and queue_name as arguments
        :param args:
        :param queue_name:
        :param delay_seconds: optional
        :return:
        """
        module_name = cls.__module__
        class_name = cls.__name__
        if DeviceUnClaimAction._arguments_ok(args):
            return super()._schedule(queue_name, module_name, class_name, args, delay_seconds)
        return None
