import logging

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.utils.aws.kinesis import send_to_firehose

from .base import DjangoBaseDataManager

logger = logging.getLogger(__name__)


class DjangoStreamDataManager(DjangoBaseDataManager):
    """
    Data manager for the old models: StreamData and StreamEventData
    """

    def _get_firehose_payload(cls, stream_data):
        """Same as StreamDataBuilderHelper.get_firehose_payload"""
        payload = {
            'stream_slug': stream_data.stream_slug,
            'project_slug': stream_data.project_slug,
            'device_slug': stream_data.device_slug,
            'variable_slug': stream_data.variable_slug,
            'type': stream_data.type,
            'dirty_ts': stream_data.dirty_ts,
            'status': stream_data.status,
            'timestamp': stream_data.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')
        }
        if stream_data.device_timestamp is not None:
            payload['device_timestamp'] = stream_data.device_timestamp
        if stream_data.int_value is not None:
            payload['int_value'] = stream_data.int_value
        if stream_data.value is not None:
            payload['value'] = stream_data.value
        if stream_data.streamer_local_id is not None:
            payload['streamer_local_id'] = stream_data.streamer_local_id
        return payload

    def get_model(cls, name):
        return {
            'data': StreamData,
            'event': StreamEventData,
        }[name]

    def send_to_firehose(cls, model, payload):
        """Sends the payload to Firehose

        Args:
            model (str): type of model sent to Firehose (ONLY 'data' is valid for this manager).
            payload (list): list of model instances.
                This list/collection should be a collection of StreamData
                instances that have to be sent to Firehose. They'll be
                serialized to a JSON payload by this method.
        """
        assert model == 'data'
        firehose_data_entries = []
        for data in payload:
            firehose_payload = cls._get_firehose_payload(data)
            assert (firehose_payload['int_value'] is not None)
            assert (firehose_payload['int_value'] == data.int_value)
            firehose_data_entries.append(firehose_payload)
        logger.debug('Using firehose (Production = {0})'.format(getattr(settings, 'PRODUCTION')))
        send_to_firehose(firehose_data_entries, batch_num=490)

    def build(cls, model, **kwargs):
        cls._validate_kwargs(model, 'build', kwargs)
        return cls.get_model(model)(**kwargs)

    def get(cls, model, **kwargs):
        cls._validate_kwargs(model, 'get', kwargs)
        try:
            return cls.get_model(model).objects.get(**kwargs)
        except cls.get_model(model).DoesNotExist:
            raise ObjectDoesNotExist(model)

    def filter_qs(cls, model, **kwargs):
        cls._validate_kwargs(model, 'filter', kwargs)
        return cls.get_model(model).objects.filter(**kwargs)

    def filter_qs_using_q(cls, model, q, extras=[]):
        assert type(q) is Q, 'Invalid argument: must be a Q object'
        cls._validate_q(model, 'filter', q, extras)
        return cls.get_model(model).objects.filter(q)

    def df_filter_qs_using_q(cls, model, q, extras=[]):
        assert type(q) is Q, 'Invalid argument: must be a Q object'
        cls._validate_q(model, 'filter', q, extras)
        return cls.get_model(model).df_objects.filter(q)
