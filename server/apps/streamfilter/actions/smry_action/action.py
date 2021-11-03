import logging

from apps.report.worker.report_generator import SummaryReportGeneratorAction

from ..action import BaseAction

logger = logging.getLogger(__name__)


class SmryAction(BaseAction):
    REQUIRED_EXTRA_KEYS = ['generator', 'notification_recipients', ]

    def __str__(self):
        return 'Summary Report Generation Action'

    def process(self, payload, in_data):
        super(SmryAction, self).process(payload, in_data)
        if not self.check_payload(payload):
            self.handle_error(str(self), "Payload is not well formatted : {}".format(payload))
            return False

        d = self._get_device(in_data.device_slug)
        if not d:
            self.handle_error(str(self), "No device found: {}".format(in_data.device_slug))
            return False

        u = self._get_user(payload['user_slug'])
        if not u:
            self.handle_error(str(self), "Expected valid user slug but got: {}".format(str(payload['user_slug'])))
            return False

        try:
            rpt_payload = payload['action']['extra_payload']
            rpt_payload.update({
                'attempt': 5,
                'generator': rpt_payload['generator'],
                'notification_recipients': rpt_payload['notification_recipients'],
                'sources': [d.slug, ],
                'org': d.org.slug,
                'user': u.slug,
                'config': {},
            })
            # Add a small delay to let data arrave to database
            SummaryReportGeneratorAction.schedule(args=rpt_payload, delay_seconds=900)
            return True
        except Exception as e:
            self.handle_error(str(self), str(e))
            return False
