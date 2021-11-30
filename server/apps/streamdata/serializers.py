import logging
import time

from rest_framework import serializers

from apps.stream.helpers import StreamDataDisplayHelper
from apps.utils.timezone_utils import str_utc

from .models import *

# Get an instance of a logger
logger = logging.getLogger(__name__)


class RedshiftTimestampField(serializers.DateTimeField):
    def to_representation(self, value):
        res = super(RedshiftTimestampField, self).to_representation(value)
        # While Redshift was configured without a timezone aware datetime
        # we want to ensure we return the DateTime in UTC
        if not res.endswith('Z') and res[-6] not in ['-', '+']:
            # Assume this dt is UTC even if not specified
            res = res + 'Z'
        return res


class StreamDataSerializer(serializers.ModelSerializer):
    stream = serializers.CharField(source='stream_slug', required=True)
    project = serializers.CharField(source='project_slug', read_only=True)
    device = serializers.CharField(source='device_slug', read_only=True)
    variable = serializers.CharField(source='variable_slug', read_only=True)
    timestamp = RedshiftTimestampField(format='%Y-%m-%dT%H:%M:%SZ')
    class Meta:
        model = StreamData
        fields = ('id', 'stream', 'project', 'device', 'variable',
                  'type', 'device_timestamp', 'timestamp', 'int_value', 'value',
                  'streamer_local_id', 'dirty_ts', 'status')

    def validate(self, data):
        """
        Check that the int_value, value and type are conistent with each othe
        """
        if not 'int_value' in data and not 'value' in data:
            raise serializers.ValidationError("Either int_value or value should be used")

        if 'int_value' in data and 'value' in data:
            raise serializers.ValidationError("Only int_value or value should be used")

        if 'int_value' in data and 'type' in data and data['type'] != 'Num':
            raise serializers.ValidationError("type should be 'Num' if int_value is used")

        if 'value' in data and ('type' not in data or data['type'] != 'ITR'):
            raise serializers.ValidationError("type should be 'ITR' or None if value is used")

        return data


class StreamIdDataSerializer(serializers.ModelSerializer):
    display_value = serializers.SerializerMethodField()
    output_value = serializers.SerializerMethodField()
    timestamp = RedshiftTimestampField(format='%Y-%m-%dT%H:%M:%SZ')

    class Meta:
        model = StreamData
        fields = ('type', 'timestamp', 'int_value', 'value', 'display_value', 'output_value', 'streamer_local_id',)

    def __init__(self, *args, **kwargs):
        many = kwargs.pop('many', True)
        stream = kwargs.pop('stream', None)
        if stream:
            self.helper = StreamDataDisplayHelper(stream=stream)
        super(StreamIdDataSerializer, self).__init__(many=many, *args, **kwargs)

    def get_display_value(self, obj):
        # display_value will sooon be removed
        if self.helper:
            if obj.value:
                out_value = self.helper.output_value(value=obj.value)
            else:
                # TODO: For now, if value is stored on int_data, then it is the old way
                #       and we need to do both input_value and output_value
                in_value = self.helper.input_value(value=obj.int_value)
                out_value = self.helper.output_value(value=in_value)

            if out_value != None:
                display_value = self.helper.format_value(out_value)
                return display_value
        return str(obj.int_value)

    def get_output_value(self, obj):
        # Convert to a user decired unit based on passed helper
        if self.helper:
            return self.helper.output_value(value=obj.value)
        return None
