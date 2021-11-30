import logging
import time

from rest_framework import serializers

from apps.stream.helpers import StreamDataDisplayHelper

from .models import *

# Get an instance of a logger
logger = logging.getLogger(__name__)


class StreamEventDataSerializer(serializers.ModelSerializer):
    stream = serializers.CharField(source='stream_slug', required=True)
    project = serializers.CharField(source='project_slug', read_only=True)
    device = serializers.CharField(source='device_slug', read_only=True)
    variable = serializers.CharField(source='variable_slug', read_only=True)
    timestamp = serializers.DateTimeField()
    data = serializers.JSONField(write_only=True, required=False)

    class Meta:
        model = StreamEventData
        fields = ('id', 'stream', 'project', 'device', 'variable',
                  's3bucket', 's3key', 'ext', 'has_raw_data', 'device_timestamp', 'timestamp',
                  'streamer_local_id', 'dirty_ts', 'status', 'data', 'extra_data')
        read_only_fields = ('s3bucket', 's3key', 'has_raw_data')

    def validate_extra_data(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('extra_data must be a valid dictionary object')
        return value


class StreamIdEventDataSerializer(serializers.ModelSerializer):
    timestamp = serializers.DateTimeField()

    class Meta:
        model = StreamEventData
        fields = ('timestamp', 'extra_data', 'streamer_local_id',)

    def __init__(self, *args, **kwargs):
        many = kwargs.pop('many', True)
        stream = kwargs.pop('stream', None)
        if stream:
            self.helper = StreamDataDisplayHelper(stream=stream)
        super(StreamIdEventDataSerializer, self).__init__(many=many, *args, **kwargs)


class StreamEventDataRawUploadSerializer(serializers.ModelSerializer):
    stream = serializers.CharField(source='stream_slug', required=True)
    timestamp = serializers.DateTimeField(help_text='Use UTC format')
    encoded_extra_data = serializers.CharField(
        source='extra_data', required=False, help_text='utf-8 encoded extra data'
    )

    class Meta:
        model = StreamEventData
        fields = ('id', 'stream', 'device_timestamp', 'timestamp',
                  'streamer_local_id', 'encoded_extra_data')
        read_only_fields = ()

    def validate_encoded_extra_data(self, value):
        """
        This serializer is used in a multipart POST, and nested dictionaries
        don't seem to be allowed. We therefore require that the extra_data
        is posted using a utf-8 encoded string.

        :param value: utf-8 encoded string
        :return: Python object: Dictionary
        """
        try:
            value = json.loads(value, encoding='utf-8')
        except Exception as e:
            raise serializers.ValidationError('Failed to deserialize value: {}'.format(e))

        if not isinstance(value, dict):
            raise serializers.ValidationError('Value should be a utf-8 encoded string')

        return value
