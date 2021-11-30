import logging

import pytz

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.emailutil.tasks import Email
from apps.emailutil.utils import EmailRecipientHelper
from apps.physicaldevice.models import Device, DeviceStatus
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerActionSoftError

logger = logging.getLogger(__name__)

class DeviceStatusCheckAction(Action):
    """
    This action will check all DeviceStatus records and send notifications for any
    that has not uploaded data in the required period
    """

    @classmethod
    def _arguments_ok(self, args):
        if 'ts' in args:
            return True
        else:
            raise WorkerActionHardError('Missing fields in argument payload.\nReceived args: {}\nRequired args fields: ts'.format(args))

    def _get_email_list(self, device_status):
        helper = EmailRecipientHelper()
        recipients = device_status.notification_recipients
        emails = helper.get_emails_from_recipient_list(recipients=recipients, org=device_status.device.org)
        return emails

    def _send_notification(self, device_status, alert):
        device = device_status.device
        assert device
        subject = _('IOTile Cloud Notification: {}'.format(device))
        template = 'device_status/notification'

        ctx = {
            'current_alert': alert,
            'device_status': device_status,
            'url': device.get_webapp_url(),
            'timestamp': timezone.now(),
            'uuid': 'DS:{}'.format(device_status.id)
        }

        user_email = Email()
        user_email.send_email(template, subject, ctx, self._get_email_list(device_status))

    def _process_checks(self):
        for device_status in DeviceStatus.objects.filter(health_check_enabled=True):
            alert = device_status.alert
            if alert != device_status.last_known_state:
                logger.info('Device is in {} state'.format(alert))
                self._send_notification(device_status, alert)

                device_status.last_known_state = alert
                device_status.save()

    def execute(self, arguments):
        super(DeviceStatusCheckAction, self).execute(arguments)
        if DeviceStatusCheckAction._arguments_ok(arguments):

            self._process_checks()

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
        if DeviceStatusCheckAction._arguments_ok(args):
            super(DeviceStatusCheckAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
