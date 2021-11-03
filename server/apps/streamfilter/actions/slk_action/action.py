import json
import logging
from urllib.parse import urlencode
import urllib.request as urlrequest

from django.conf import settings

from apps.streamfilter.models import StreamFilter
from apps.physicaldevice.models import Device
from ..action import BaseAction

logger = logging.getLogger(__name__)


class SlkAction(BaseAction):

    REQUIRED_EXTRA_KEYS = ['slack_webhook', 'custom_note']

    def __str__(self):
        return 'Slack Notification Action'

    class Slack():

        def __init__(self, url=""):
            self.url = url
            self.opener = urlrequest.build_opener(urlrequest.HTTPHandler())

        def notify(self, **kwargs):
            """
            Send message to slack API
            """
            return self.send(kwargs)

        def send(self, payload):
            """
            Send payload to slack API
            """
            payload_json = json.dumps(payload)
            data = urlencode({"payload": payload_json})
            req = urlrequest.Request(self.url)
            response = self.opener.open(req, data.encode('utf-8')).read()
            return response.decode('utf-8')

    def process(self, payload, in_data):
        super(SlkAction, self).process(payload, in_data)
        if not self.check_payload(payload):
            self.handle_error(str(self), "Payload is not well formatted : {}".format(payload))
            return False

        f = self._get_filter(payload)
        if not f:
            return False

        s = self._get_stream(in_data.stream_slug)
        if not s:
            return False

        if f.device_id:
            device = f.device
        else:
            device = Device.objects.get(slug=in_data.device_slug)

        value = self._get_data_value(s, in_data.value)
        try:
            trigger_text = ""
            for trigger in payload['transition']['triggers']:
                text = "{} {} {}, ".format(trigger['get_operator_display'], trigger['user_threshold'], trigger['user_unit_full'])
                trigger_text += text
            payload['on'] = 'into' if payload['on'] == 'entry' else 'out of'
            extra = payload['action']['extra_payload']
            ts = self._get_formatted_ts(in_data.timestamp)

            if extra['custom_note']:
                body = extra['custom_note']
            else:
                body = """
                Stream Filter Notification:

                *Stream Filter {label} has transitioned {on} state {state}*:

                - Device ID: {device_slug}
                - Device label: {device_label}
                - Stream: {stream}
                - Project: {project}

                Event triggered at {ts} because a data point of value {value} is {trigger}
                """

            ctx = {
                'state': payload['state']['label'],
                'label': f.name,
                'device_slug': device.slug,
                'device_label': device.label,
                'stream': s.label_or_slug,
                'project': str(f.project),
                'on': 'into' if payload['on'] == 'entry' else 'from',
                'ts': ts,
                'trigger': trigger_text,
                'value': value
            }
            txt_message = self._process_custom_message(msg=body, ctx=ctx)

            if settings.SERVER_TYPE in ['prod', 'stage']:
                s = self.Slack(url=extra['slack_webhook'])
                ok = s.notify(text=txt_message)
                return ok == 'ok'
            else:
                logger.info(txt_message)
                return True
        except Exception as e:
            self.handle_error(str(self), str(e))
            return False


