import logging
from datetime import timedelta

import pytz

from django.conf import settings

from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError
from apps.utils.aws.redshift import get_ts_from_redshift
from apps.utils.data_helpers.manager import DataManager
from apps.utils.iotile.variable import SYSTEM_VID

from .handle_reboot import HandleRebootAction

logger = logging.getLogger(__name__)


class HandleDelayAction(Action):
    device = None
    report_id = None
    project = None

    def _fix_data_backward(self, start_id, end_id):
        reboots = DataManager.filter_qs('data', streamer_local_id__gte=start_id, streamer_local_id__lte=end_id,
                                        device_slug=self.device.slug, project_slug=self.project.slug,
                                        variable_slug__contains=SYSTEM_VID['REBOOT']).order_by("streamer_local_id")
        reboot_ids = []
        for reboot in reboots:
            reboot_ids += [reboot.streamer_local_id]
        if reboots.count() > 0:
            last_reboot = reboots.last()
            if last_reboot.dirty_ts or last_reboot.status == 'drt':
                clean_data = DataManager.filter_qs('data', streamer_local_id__gte=reboot_ids[-1], streamer_local_id__lt=end_id,
                                                   device_slug=self.device.slug, project_slug=self.project.slug)
                trusted_data = DataManager.filter_qs('data', streamer_local_id=end_id, device_slug=self.device.slug, project_slug=self.project.slug).last()
                if trusted_data:
                    logger.info("Found trusted data point at the end of block. Timestamp: {}".format(
                        trusted_data.timestamp
                    ))
                    base_ts = get_ts_from_redshift(trusted_data.timestamp - timedelta(seconds=trusted_data.device_timestamp))
                    logger.info("Based ts: {}".format(base_ts))
                    logger.info("Fixing clean data from id {} to {}".format(reboot_ids[-1], end_id))
                    for item in clean_data:
                        # Fix data no matter if it's clean or dirty
                        item.timestamp = base_ts + timedelta(seconds=item.device_timestamp)
                        item.dirty_ts = False
                        item.status = 'cln'
                        DataManager.save('data', item)
                else:
                    raise WorkerActionHardError("Trusted data not found at the end of block")
            reboot_args = {
                'device_slug': self.device.slug,
                'project_id': str(self.project.id),
                'block_end_id': end_id,
                'block_start_id': start_id - 1,
                'reboot_ids': reboot_ids
            }
            handle_reboot = HandleRebootAction()
            handle_reboot.execute(arguments=reboot_args)

    def execute(self, arguments):
        super(HandleDelayAction, self).execute(arguments)
        if 'device_slug' in arguments and 'start_id' in arguments and 'end_id' in arguments and 'report_id' in arguments and 'project_id' in arguments:
            try:
                self.report_id = arguments['report_id']
                self.device = Device.objects.get(slug=arguments['device_slug'])
                self.project = Project.objects.get(id=arguments['project_id'])
                self._fix_data_backward(arguments['start_id'], arguments['end_id'])
            except Device.DoesNotExist:
                raise WorkerActionHardError("Device with slug {} not found !".format(arguments['device_slug']))
            except Project.DoesNotExist:
                raise WorkerActionHardError("Project with id {} not found !".format(arguments['project_id']))
        else:
            raise WorkerActionHardError('Missing fields in arguments payload. Error comes from task HandleDelayAction, received args: {}'.format(arguments))

    @classmethod
    def schedule(cls, args, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        module_name = cls.__module__
        class_name = cls.__name__
        if 'device_slug' in args and 'start_id' in args and 'end_id' in args and 'report_id' in args and 'project_id' in args:
            super(HandleDelayAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
        else:
            raise WorkerActionHardError('Missing fields in argument payload.\nReceived args: {}\nRequired args fields: device_slug, report_id, start_id, end_id, project_id'.format(
                args))
