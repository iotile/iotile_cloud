import importlib
import logging

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.physicaldevice.models import Device
from apps.stream.models import StreamId
from apps.streamdata.utils import get_stream_output_mdo, get_stream_output_unit
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.timezone_utils import formatted_ts

from ..models import StreamFilter

user_model = get_user_model()

logger = logging.getLogger(__name__)


class BaseAction(object):
    payload = None
    in_data = None
    REQUIRED_PAYLOAD_KEYS = ['action', 'on', 'state', 'transition', 'filter']
    REQUIRED_EXTRA_KEYS = []

    def process(self, payload, in_data):
        self.payload = payload
        self.in_data = in_data
        return False

    def get_derived_stream_data(self):
        return None

    def check_payload(self, payload):
        for key in self.REQUIRED_PAYLOAD_KEYS:
            if key not in payload:
                return False
        if self.REQUIRED_EXTRA_KEYS:
            if 'extra_payload' not in payload['action']:
                return False
            for key in self.REQUIRED_EXTRA_KEYS:
                if key not in payload['action']['extra_payload']:
                    return False
        return True

    def handle_error(self, class_name, message):
        msg = "STREAM FILTER: Error occurs when executing action {} : {}".format(class_name, message)
        logger.error(msg)
        sns_staff_notification(msg)

    def _get_filter(self, payload):
        filter_slug = payload['filter']
        try:
            return StreamFilter.objects.get(slug=filter_slug)
        except StreamFilter.DoesNotExist as e:
            self.handle_error(str(self), str(e))
            return None

    def _get_stream(self, slug):
        try:
            return StreamId.objects.get(slug=slug)
        except StreamId.DoesNotExist as e:
            logger.error(str(e))
            return None

    def _get_device(self, slug):
        try:
            return Device.objects.get(slug=slug)
        except Device.DoesNotExist as e:
            logger.error(str(e))
            return None

    def _get_user(self, slug):
        try:
            return user_model.objects.get(slug=slug)
        except user_model.DoesNotExist as e:
            logger.error(str(e))
            return None

    def _get_formatted_ts(self, dt):
        return formatted_ts(dt)

    def _get_data_value(self, stream, value):
        output_unit = get_stream_output_unit(stream)
        output_mdo = get_stream_output_mdo(stream)
        if output_mdo and output_unit:
            output_value = '{0:.2f}'.format(output_mdo.compute(value))
            output_unit_name = output_unit.unit_short
        else:
            output_value = '{0:.2f}'.format(value)
            output_unit_name = ""
        value = '{0} {1}'.format(output_value, output_unit_name)
        return value

    def _process_custom_message(self, msg, ctx):
        try:
            text_message = msg.format(**ctx)
        except Exception as e:
            text_message = '{ts}: Stream Filter "{label}" Error: {e}'.format(ts=ctx['ts'], label=ctx['label'], e=e)
        return text_message

    def __str__(self):
        return 'BaseAction'
