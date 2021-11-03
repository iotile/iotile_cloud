import logging

from apps.stream.models import StreamId
from apps.streamdata.helpers import StreamDataBuilderHelper

from ..action import BaseAction

logger = logging.getLogger(__name__)


class DrvAction(BaseAction):
    REQUIRED_EXTRA_KEYS = []
    derived_data = None

    def __str__(self):
        return 'Derive Stream Action'

    def get_derived_stream_data(self):
        if self.derived_data:
            return self.derived_data
        return None

    def process(self, payload, in_data):
        super(DrvAction, self).process(payload, in_data)
        if not self.check_payload(payload):
            self.handle_error(str(self), "Payload is not well formatted : {}".format(payload))
            return False
        try:
            extra = payload['action'].get('extra_payload')
            if extra and extra.get('output_stream'):
                helper = StreamDataBuilderHelper()
                output_stream_slug = extra.get('output_stream')
                # Value will be calculated using output stream mdo
                self.derived_data = helper.build_data_obj(stream_slug=output_stream_slug,
                                                          streamer_local_id=in_data.streamer_local_id,
                                                          device_timestamp=in_data.device_timestamp,
                                                          timestamp=in_data.timestamp,
                                                          int_value=in_data.int_value)
                # print('==> Derived Data: {}'.format(self.derived_data))
            return True
        except Exception as e:
            self.handle_error(str(self), str(e))
            return False
