import json
import logging

from apps.report.worker.report_generator import ReportGeneratorAction
from apps.utils.timezone_utils import str_utc

from ..action import BaseAction

logger = logging.getLogger(__name__)


class RptAction(BaseAction):
    REQUIRED_EXTRA_KEYS = ['rpt', ]

    def __str__(self):
        return 'Report Generation Action'

    def process(self, payload, in_data):
        super(RptAction, self).process(payload, in_data)
        if not self.check_payload(payload):
            self.handle_error(str(self), "Payload is not well formatted : {}".format(payload))
            return False

        d = self._get_device(in_data.device_slug)
        if not d:
            return False

        try:
            rpt = payload['action']['extra_payload']['rpt']
            rpt_payload = {
                'rpt': rpt,
                'attempt': 1,
            }
            ReportGeneratorAction.schedule(args=rpt_payload)
            return True
        except Exception as e:
            self.handle_error(str(self), str(e))
            return False
