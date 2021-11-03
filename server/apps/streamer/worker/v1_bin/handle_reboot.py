import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Max
from django.utils.dateparse import parse_datetime

from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerActionSoftError
from apps.streamer.models import Streamer
from apps.utils.aws.redshift import get_ts_from_redshift
from apps.utils.data_helpers.manager import DataManager
from apps.utils.iotile.variable import SYSTEM_VID

from .delay_checker import DelayChecker

logger = logging.getLogger(__name__)

DELAY_SECONDS = 5 * 60  # in seconds


class HandleRebootAction(Action):
    """
    block_start_id is the device's last_known_id = incremental id of the system report processed before this report
    block_end_id = incremental id of the report we're handling
    """
    device = None
    reboot_ids = None
    block_start_id = None
    block_end_id = None
    project = None

    def _fix_dirty_data_backward(self, start_id, end_id, next_base_ts):
        """
            Fix dirty data heuristically, assuming that this data block is recorded right before the heuristic_next_reboot
            Dirty data is between the first reboot and the last reboot in a report (if there are more than 1 reboot)
            Because streamer_local_id and device_timestamp are always INCREASE together, the end_id point has the greatest device_timestamp
            :param next_base_ts: base datetime
            :param start_id: fix data from this id (inclusive)
            :param end_id: fix data up to this id (exclusive)
            :return: the last timestamp of the series (a datetime object)
            """
        data = DataManager.filter_qs('data', streamer_local_id__gte=start_id, streamer_local_id__lt=end_id,
                                     device_slug=self.device.slug, project_slug=self.project.slug)
        device_timestamp_max = DataManager.filter_qs('data', streamer_local_id__gte=start_id, streamer_local_id__lt=end_id,
                                                     device_slug=self.device.slug, project_slug=self.project.slug).aggregate(Max('device_timestamp'))
        logger.info("Fixing dirty data from id {} to id {} with next reboot timestamp {}".format(start_id, end_id, next_base_ts))
        if device_timestamp_max['device_timestamp__max']:
            base_ts = next_base_ts - timedelta(seconds=device_timestamp_max['device_timestamp__max'])
            for item in data:
                item.timestamp = base_ts + timedelta(seconds=item.device_timestamp)
                item.dirty_ts = True
                item.status = 'drt'
                DataManager.save('data', item)
                if item.device_timestamp == device_timestamp_max['device_timestamp__max']:
                    end = DataManager.filter_qs('data', streamer_local_id=end_id, device_slug=self.device.slug, project_slug=self.project.slug).last()
                    if end and end.timestamp and end.device_timestamp:
                        # assert(item.timestamp == end.timestamp - timedelta(seconds=end.device_timestamp))
                        logger.info("Comparing item ts {} and end ts {}".format(item.timestamp, end.timestamp - timedelta(seconds=end.device_timestamp)))
        else:
            base_ts = next_base_ts
        logger.info("Base dirty timestamp: {}".format(base_ts))
        return base_ts

    def _fix_clean_data_backward(self, end_id, next_base_ts):
        start_id = self.block_start_id + 1
        logger.info("Fixing clean data from id {} to id {} with next reboot timestamp {}".format(start_id, end_id, next_base_ts))
        data = DataManager.filter_qs('data', streamer_local_id__gte=start_id, streamer_local_id__lt=end_id,
                                     device_slug=self.device.slug, project_slug=self.project.slug)
        base_timestamp = None
        previous_sys_report = None
        try:
            sys_streamer = self.device.streamers.get(is_system=True)
        except Streamer.DoesNotExist:
            sys_streamer = None
        if sys_streamer:
            previous_sys_report = sys_streamer.reports.filter(incremental_id=self.block_start_id).order_by("sent_timestamp").last()
        if previous_sys_report and previous_sys_report.device_sent_timestamp:
            logger.info("Found trusted report {}: incremental_id = {},ts = {}, device ts = {}".format(str(previous_sys_report.id), previous_sys_report.incremental_id,
                                                                                                      previous_sys_report.sent_timestamp,
                                                                                                      previous_sys_report.device_sent_timestamp))
            base_timestamp = previous_sys_report.sent_timestamp - timedelta(seconds=previous_sys_report.device_sent_timestamp)
        else:
            trusted_reboot = DataManager.filter_qs('data', streamer_local_id__lt=end_id, streamer_local_id__gt=0, device_slug=self.device.slug,
                                                   variable_slug__contains=SYSTEM_VID['REBOOT'], dirty_ts=False).order_by('-streamer_local_id').first()
            if trusted_reboot and trusted_reboot.device_timestamp and trusted_reboot.timestamp:
                logger.info("Found trusted reboot at id {} and ts {}".format(trusted_reboot.streamer_local_id, trusted_reboot.timestamp))
                base_timestamp = trusted_reboot.timestamp - timedelta(seconds=trusted_reboot.device_timestamp)
        if base_timestamp:
            for item in data:
                item.timestamp = get_ts_from_redshift(base_timestamp + timedelta(seconds=item.device_timestamp))
                item.status = 'cln'
                DataManager.save('data', item)
        else:
            # data from start_id up to end_id will be treated as dirty
            logger.info("Base ts not found. Fix as dirty data")
            self._fix_dirty_data_backward(start_id, end_id, next_base_ts)

    def fix_data_backward(self):
        if len(self.reboot_ids) > 0:
            report_clean_reboot = DataManager.filter_qs('data', streamer_local_id=self.reboot_ids[-1], device_slug=self.device.slug,
                                                        project_slug=self.project.slug).last()
            if report_clean_reboot:
                logger.info("Getting timestamp of report_clean_reboot: {}".format(report_clean_reboot.timestamp))
                next_base_ts = get_ts_from_redshift(report_clean_reboot.timestamp - timedelta(seconds=report_clean_reboot.device_timestamp))
                logger.info("Timestamp of next_base_ts: {}".format(next_base_ts))
                if len(self.reboot_ids) == 1:
                    self._fix_clean_data_backward(self.reboot_ids[0], next_base_ts)
                elif len(self.reboot_ids) > 1:

                    for i in range(1, len(self.reboot_ids)):
                        next_base_ts = self._fix_dirty_data_backward(self.reboot_ids[len(self.reboot_ids) - i - 1], self.reboot_ids[len(self.reboot_ids) - i], next_base_ts)
                    self._fix_clean_data_backward(self.reboot_ids[0], next_base_ts)
                DataManager.filter_qs('data', device_slug=self.device.slug, project_slug=self.project.slug, streamer_local_id__gte=self.reboot_ids[-1],
                                      streamer_local_id__lte=self.block_end_id).update(status='cln')
            else:
                raise WorkerActionHardError("Report clean reboot with id {} not found !".format(self.reboot_ids[-1]))

    def execute(self, arguments):
        super(HandleRebootAction, self).execute(arguments)
        if 'device_slug' in arguments and 'block_start_id' in arguments and 'reboot_ids' in arguments and 'block_end_id' in arguments and 'project_id' in arguments:
            try:
                self.device = Device.objects.get(slug=arguments['device_slug'])
                self.block_start_id = arguments['block_start_id']
                self.reboot_ids = arguments['reboot_ids']
                self.block_end_id = arguments['block_end_id']
                self.project = Project.objects.get(id=arguments['project_id'])
            except Device.DoesNotExist:
                raise WorkerActionHardError("Device with slug {} not found !".format(arguments['device_slug']))
            except Project.DoesNotExist:
                raise WorkerActionHardError("Project with id {} not found !".format(arguments['project_id']))
            checker = DelayChecker(self, self.device, self.project, arguments['block_start_id'], arguments['block_end_id'])
            if checker.ready_to_process():
                logger.info("Data ready to process")
                self.fix_data_backward()
                checker.delete_count()
            else:
                if checker.continue_delay():
                    logger.info("Data not ready to process. Schedule to retry later")
                    HandleRebootAction.schedule(args=arguments, delay_seconds=DELAY_SECONDS)
        else:
            raise WorkerActionHardError('Missing fields in arguments payload. Error comes from task HandleRebootAction, received args: {}'.format(arguments))

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
        if 'device_slug' in args and 'block_end_id' in args and 'block_start_id' in args and 'reboot_ids' in args and 'project_id' in args:
            super(HandleRebootAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
        else:
            raise WorkerActionHardError('Missing fields in argument payload.\nReceived args: {}\nRequired args fields: device_slug, block_end_id, block_start_id, reports_ids, project_id'.format(args))
