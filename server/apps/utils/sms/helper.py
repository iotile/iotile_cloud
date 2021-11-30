import logging

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from django.conf import settings

logger = logging.getLogger(__name__)


class SmsHelper(object):
    _from_phone = None
    _account_sid = None
    _auth_token = None

    def __init__(self):
        self._account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID')
        self._auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN')
        self._from_phone = getattr(settings, 'TWILIO_FROM_NUMBER')

    def send(self, to_number, body):
        client = Client(self._account_sid, self._auth_token)
        body = '[IOTile Cloud] ' + body

        try:
            message = client.messages.create(
                to=to_number,
                from_=self._from_phone,
                body=body)
        except TwilioRestException as e:
            logger.warning('TwilioRestException(status={0}): {1}'.format(
                e.status, e.msg
            ))
            return False, e.msg

        return True, message.sid

    @property
    def from_number(self):
        return self._from_phone

