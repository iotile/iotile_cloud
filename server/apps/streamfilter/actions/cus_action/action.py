import json
import logging

from apps.utils.aws.sns import _sns_text_based_notification
from apps.utils.data_helpers.manager import DataManager
from apps.utils.timezone_utils import str_utc

from ..action import BaseAction

logger = logging.getLogger(__name__)


class CusAction(BaseAction):
    REQUIRED_EXTRA_KEYS = ['sns_topic']

    def __str__(self):
        return 'Custom Action'

    def process(self, payload, in_data):
        super(CusAction, self).process(payload, in_data)
        if not DataManager.is_instance('event', in_data) or not self.check_payload(payload):
            self.handle_error(str(self), "Payload is not well formatted : {}".format(payload))
            return False
        try:
            sns_topic = payload['action']['extra_payload']['sns_topic']
            sns_payload = {
                "uuid": str(in_data.uuid),
                "project": in_data.project_slug,
                "device": in_data.device_slug,
                "stream": in_data.stream_slug,
                "timestamp": str_utc(in_data.timestamp),
                "bucket": in_data.s3bucket,
                "key": in_data.s3key
            }
            _sns_text_based_notification(sns_topic, json.dumps(sns_payload))
            return True
        except Exception as e:
            self.handle_error(str(self), str(e))
            return False
