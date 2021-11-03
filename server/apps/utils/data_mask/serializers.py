import json
import pytz

from django.conf import settings

from rest_framework import serializers

from apps.utils.timezone_utils import formatted_ts


class DeviceDataMaskSerializer(serializers.Serializer):
    start = serializers.DateTimeField(format='%Y-%m-%dT%H:%M:%SZ', required=False)
    end = serializers.DateTimeField(format='%Y-%m-%dT%H:%M:%SZ', required=False)

    def validate(self, data):
        """
        Check that the start is before the end and that at least one is set
        """
        has_start = 'start' in data
        has_end = 'end' in data
        if not has_start and not has_end:
            raise serializers.ValidationError("At least one of start/end should be defined")
        if has_start and has_end:
            if data.get('start') > data.get('end'):
                raise serializers.ValidationError("Start is after end")
        if has_start:
            data['start'] = formatted_ts(data.get('start'))
        if has_end:
            data['end'] = formatted_ts(data.get('end'))

        return data


