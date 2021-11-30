import json
import logging
import uuid

from django.conf import settings

from apps.emailutil.tasks import Email
from apps.emailutil.utils import EmailRecipientHelper

from ..action import BaseAction

logger = logging.getLogger(__name__)


class EmlAction(BaseAction):

    REQUIRED_EXTRA_KEYS = ['notification_recipient']

    def __str__(self):
        return 'Email Notification Action'

    def _get_email_list(self, extra, org):
        helper = EmailRecipientHelper()
        recipients = extra['notification_recipient']
        if isinstance(recipients, str):
            if recipients[0] == '{':
                recipients = json.loads(recipients)
        if isinstance(recipients, dict):
            # Handle backwards compatible payloads
            new_recipients = []
            if 'org' in recipients:
                new_recipients.append('org:{}'.format(recipients['org']))
            if 'users' in recipients:
                for u in recipients['users']:
                    new_recipients.append('user:{}'.format(u))
            if 'emails' in recipients:
                for e in recipients['emails']:
                    new_recipients.append('email:{}'.format(e))
            recipients = new_recipients
        if isinstance(recipients, list):
            emails = helper.get_emails_from_recipient_list(recipients=recipients, org=org)
        else:
            logger.warning('Badly formatted recipient list: {}'.format(recipients))
            emails = []
        return emails

    def process(self, payload, in_data):
        super(EmlAction, self).process(payload, in_data)

        if not self.check_payload(payload):
            self.handle_error(str(self), "Payload is not well formatted : {}".format(payload))
            return False

        f = self._get_filter(payload)
        if not f:
            return False

        s = self._get_stream(in_data.stream_slug)
        if not s:
            return False

        try:
            value = self._get_data_value(s, in_data.value)
            ts = self._get_formatted_ts(in_data.timestamp)
            notification_id = uuid.uuid4()
            url = s.device.get_webapp_url()

            extra = payload['action']['extra_payload']
            if 'body' in extra:

                body = extra['body']

                ctx = {
                    'label': f.name,
                    'state': payload['state']['label'],
                    'stream': s.label_or_slug,
                    'device': s.device.label if s.device.label else s.device.slug,
                    'project': s.project.name,
                    'on': 'into' if payload['on'] == 'entry' else 'from',
                    'ts': ts,
                    'value': value
                }

                text_message = self._process_custom_message(msg=body, ctx=ctx)

                ctx = {
                    'uuid': notification_id,
                    'url': url,
                    'body': text_message
                }
                template = 'streamfilter/notifications/custom'

            else:
                custom_note = ''
                if 'custom_note' in extra:
                    custom_note = extra['custom_note']
                ctx = {
                    'uuid': notification_id,
                    'source_slug': s.slug,
                    'source_label': s.project_ui_label,
                    'device': s.device,
                    'project': s.project,
                    'org': s.org,
                    'url': url,
                    'source_type': 'stream',
                    'timestamp': ts,
                    'level': 'INFO',
                    'transition': payload['transition'],
                    'data': value,
                    'custom_note': custom_note
                }
                template = 'streamfilter/notifications/eml'

            user_email = Email()
            subject = 'IOTile Cloud Notification'
            user_email.send_email(template, subject, ctx, self._get_email_list(extra, s.org))

            return True
        except Exception as e:
            self.handle_error(str(self), str(e))
            return False
