import logging

from django.conf import settings

from apps.utils.sms.helper import SmsHelper

from ..action import BaseAction

logger = logging.getLogger(__name__)


class SmsAction(BaseAction):

    REQUIRED_EXTRA_KEYS = ['body', 'number']

    def __str__(self):
        return 'SMS Notification Action'

    def process(self, payload, in_data):
        super(SmsAction, self).process(payload, in_data)
        if not self.check_payload(payload):
            self.handle_error(str(self), "Payload is not well formatted : {}".format(payload))
            return False

        f = self._get_filter(payload)
        if not f:
            return False

        s = self._get_stream(in_data.stream_slug)
        if not s:
            return False

        value = self._get_data_value(s, in_data.value)

        extra = payload['action']['extra_payload']
        ts = self._get_formatted_ts(in_data.timestamp)

        payload['on'] = 'into' if payload['on'] == 'entry' else 'out of'
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

        if text_message:
            number = extra['number']
            sms_helper = SmsHelper()
            ok, resp = sms_helper.send(to_number=number, body=text_message)
            if not ok:
                self.handle_error(str(self), 'Error sending SMS: {}'.format(resp))
                return False

        return True
