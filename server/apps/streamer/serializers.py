from rest_framework import serializers

from apps.utils.iotile.streamer import STREAMER_SELECTOR

from .models import *


class StreamerSerializer(serializers.ModelSerializer):
    device = serializers.SlugRelatedField(
        queryset=Device.objects.all(),
        slug_field='slug'
     )
    is_system = serializers.SerializerMethodField()
    class Meta:
        model = Streamer
        fields = ('id', 'slug', 'device', 'process_engine_ver',
                  'index', 'last_id', 'last_reboot_ts', 'is_system', 'selector')
        read_only_fields = ('slug', 'is_system', 'process_engine_ver')

    def get_is_system(self, obj):
        return obj.selector == STREAMER_SELECTOR['SYSTEM']


class StreamerReportSerializer(serializers.ModelSerializer):
    created_by = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    streamer = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    class Meta:
        model = StreamerReport
        fields = ('id', 'original_first_id', 'original_last_id', 'actual_first_id', 'actual_last_id',
                  'streamer', 'sent_timestamp', 'device_sent_timestamp', 'incremental_id', 'time_epsilon',
                  'created_on', 'created_by')
        read_only_fields = ('original_first_id', 'original_last_id', 'actual_first_id', 'actual_last_id',
                            'streamer', 'created_on', 'created_by')


class StreamerReportJsonPostSerializer(serializers.ModelSerializer):
    format = serializers.CharField(required=False)
    device = serializers.IntegerField(required=False)
    streamer_index = serializers.IntegerField(required=False)
    streamer_selector = serializers.IntegerField(required=False)
    lowest_id = serializers.IntegerField(required=False)
    highest_id = serializers.IntegerField(required=False)
    events = serializers.JSONField(required=False)
    data = serializers.JSONField(required=False)

    class Meta:
        model = StreamerReport
        fields = (
            'format',
            'device',
            'streamer_index',
            'streamer_selector',
            'device_sent_timestamp',
            'incremental_id',
            'lowest_id',
            'highest_id',
            'events',
            'data'
            )

            
class StreamerReportJsonV2PostSerializer(serializers.ModelSerializer):
    format = serializers.CharField(required=True)
    device = serializers.IntegerField(required=True)
    streamer_index = serializers.IntegerField(required=True)
    device_sent_timestamp = serializers.IntegerField(required=True)
    streamer_selector = serializers.IntegerField(required=True)
    lowest_id = serializers.IntegerField(required=True)
    highest_id = serializers.IntegerField(required=True)
    events = serializers.JSONField(required=False)
    data = serializers.JSONField(required=False)

    class Meta:
        model = StreamerReport
        fields = (
            'format',
            'device',
            'streamer_index',
            'streamer_selector',
            'device_sent_timestamp',
            'incremental_id',
            'lowest_id',
            'highest_id',
            'events',
            'data'
            )
