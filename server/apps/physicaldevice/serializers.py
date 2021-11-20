import json

import pytz
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count
from rest_framework import serializers

from apps.deviceauth.serializers import DeviceKeySerializer, DeviceKey
from apps.devicescript.models import DeviceScript
from apps.devicescript.serializers import DeviceScriptReadOnlySerializer
from apps.stream.models import StreamId
from apps.streamer.models import StreamerReport
from apps.streamfilter.dynamodb import DynamoFilterLogModel
from apps.utils.data_helpers.manager import DataManager
from apps.utils.timezone_utils import formatted_ts

from .claim_utils import DEFAULT_IOTILE_DEVICE_NAME_FORMAT
from .models import *


class DeviceSerializer(serializers.ModelSerializer):
    org = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug'
    )
    template = serializers.SlugRelatedField(
        queryset=DeviceTemplate.objects.all(),
        slug_field='slug'
    )
    sg = serializers.SlugRelatedField(
        queryset=SensorGraph.objects.all(),
        slug_field='slug',
        required=False
    )
    claimed_by = serializers.SlugRelatedField(
        queryset=get_user_model().objects.all(),
        slug_field='slug',
        required=False
    )
    gid = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = (
            'id',
            'slug',
            'gid',
            'label',
            'active',
            'external_id',
            'sg',
            'template',
            'org',
            'project',
            'lat',
            'lon',
            'state',
            'busy',
            'created_on',
            'claimed_by',
            'claimed_on'
        )
        read_only_fields = (
            'created_on',
            'slug',
            'state',
            'busy',
            'claimed_by',
            'claimed_on'
        )

    def get_gid(self, obj):
        return obj.formatted_gid


class DeviceUserSerializer(DeviceSerializer):
    template = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug'
    )
    claimed_by = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug'
    )

    class Meta(DeviceSerializer.Meta):
        read_only_fields = (
            'created_on',
            'slug',
            'org',
            'template',
            'claimed_by',
            'claimed_on'
        )


class DeviceIsClaimableSerializer(serializers.Serializer):
    slugs = serializers.ListField()


class DeviceClaimSerializer(serializers.Serializer):
    device = serializers.CharField(max_length=22)
    project = serializers.CharField(max_length=36)


class DeviceUnclaimSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=100, default=DEFAULT_IOTILE_DEVICE_NAME_FORMAT)
    clean_streams = serializers.BooleanField(required=False, default=False)


class DeviceUpgradeSerializer(serializers.Serializer):
    firmware = serializers.CharField(max_length=10)


class DeviceFirmwareVersionUpdateSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    actual_script = serializers.CharField(max_length=36)


class DeviceStatusReadOnlySerializer(serializers.ModelSerializer):

    class Meta:
        model = DeviceStatus
        fields = ('alert', 'last_report_ts', 'last_known_id', 'last_known_state',
                  'health_check_enabled', 'health_check_period', 'notification_recipients')
        read_only_fields = ('alert', 'last_report_ts', 'last_known_id', 'last_known_state')


class DeviceStatusWriteOnlySerializer(serializers.ModelSerializer):

    class Meta:
        model = DeviceStatus
        fields = ('health_check_enabled', 'health_check_period', 'notification_recipients')


class DeviceFilterLogSerializer(serializers.Serializer):

    class Meta:
        model = Device
        fields = ('slug', 'device_filter_logs')
        read_only_fields = ['slug', ]

    device_filter_logs = serializers.SerializerMethodField()

    def get_device_filter_logs(self, object):
        logs_obj = []
        logs = []
        for stream in object.streamids.all():
            try:
                logs_obj += DynamoFilterLogModel.target_index.query(stream.slug)
            except Exception as e:
                logger.error(str(e))
        for l in logs_obj:
            logs += [{
                'uuid': l.uuid,
                'target_slug': l.target_slug,
                'timestamp': l.timestamp,
                'src': l.src,
                'dst': l.dst,
                'triggers': l.triggers
            }]
        return logs


class DeviceDataTrimSerializer(serializers.Serializer):
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


class DeviceExtraInfoSerializer(DeviceSerializer):
    stream_counts = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = (
            'id',
            'slug',
            'project',
            'label',
            'active',
            'created_on',
            'claimed_by',
            'claimed_on',
            'stream_counts'
        )
        read_only_fields = (
            'created_on',
            'slug',
            'claimed_by',
            'claimed_on'
        )

    def get_stream_counts(self, obj):
        distinct_data_streams = DataManager.filter_qs('data', device_slug=obj.slug).order_by('stream_slug').values('stream_slug').annotate(total=Count('id'))
        distinct_event_streams = DataManager.filter_qs('event', device_slug=obj.slug).order_by('stream_slug').values('stream_slug').annotate(total=Count('id'))

        stream_dict = {}

        for item in distinct_data_streams:
            stream_slug = item.pop('stream_slug')
            if 'total' in item:
                item['data_cnt'] = item.pop('total')
            if stream_slug in stream_dict:
                stream_dict[stream_slug].update(item)
            else:
                stream_dict[stream_slug] = item
            stream_dict[stream_slug]['has_streamid'] = False

        for item in distinct_event_streams:
            stream_slug = item.pop('stream_slug')
            if 'total' in item:
                item['event_cnt'] = item.pop('total')
            if stream_slug in stream_dict:
                stream_dict[stream_slug].update(item)
            else:
                stream_dict[stream_slug] = item
            stream_dict[stream_slug]['has_streamid'] = False

        for streamid in StreamId.objects.filter(device=obj, block__isnull=True):
            if streamid.slug in stream_dict:
                stream_dict[streamid.slug]['has_streamid'] = True

        return stream_dict


class DeviceResetSerializer(serializers.Serializer):
    full = serializers.BooleanField(
        default=True,
        required=False,
        help_text='Allows old data to be reloaded. Allows data to be reloaded'
    )
    include_properties = serializers.BooleanField(
        default=True,
        required=False,
        help_text='Delete properties'
    )
    include_notes_and_locations = serializers.BooleanField(
        default=True,
        required=False,
        help_text='Delete Stream/Device Notes and Locations'
    )


class ManufacturingDataSerializer(DeviceSerializer):
    template = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug'
    )
    claimed = serializers.SerializerMethodField()

    class Meta(DeviceSerializer.Meta):
        fields = (
            'id',
            'slug',
            'gid',
            'created_on',
            'slug',
            'template',
            'sg',
            'claimed',
        )
        read_only_fields = (
            'id',
            'slug',
            'gid',
            'created_on',
            'slug',
            'template',
            'sg',
        )

    def get_claimed(self, obj):
        # Hides user information as it is confidential to an org
        if obj.project is not None:
            return True
        return False


class ManufacturingDataKeysSerializer(ManufacturingDataSerializer):
    keys = serializers.SerializerMethodField()

    def get_keys(self, obj):
        qs = DeviceKey.objects.filter(slug=obj.slug, downloadable=True)
        return DeviceKeySerializer(qs, many=True).data

    class Meta(DeviceSerializer.Meta):
        fields = (
            'id',
            'slug',
            'gid',
            'created_on',
            'slug',
            'template',
            'sg',
            'claimed',
            'keys',
        )
        read_only_fields = (
            'id',
            'slug',
            'gid',
            'created_on',
            'slug',
            'template',
            'sg',
            'keys',
        )


AVAILABLE_SENSOR_GRAPH = {
    "edge-v1-0-0",
    "broker-worker-v1-0-0",
    "connector-smt-generic-machine-v1-0-0",
    "connector-smt-generic-insp-v1-0-0",
    "connector-smt-generic-pnp-v1-0-0",
    "forwarder-generic-v1-0-0",
}

class ManufacturingDataVirtualDeviceSerializer(DeviceSerializer):
    """Serializer to create virtual devices with org api key"""
    org = serializers.SlugRelatedField(
        queryset=Org.objects.all(),
        slug_field='slug',
        required=True,
    )
    user = serializers.SlugRelatedField(
        queryset=get_user_model().objects.filter(is_active=True, is_staff=True),
        slug_field='slug',
        required=True
    )
    sg = serializers.SlugRelatedField(
        queryset=SensorGraph.objects.filter(slug__in=AVAILABLE_SENSOR_GRAPH),
        slug_field='slug',
        required=True
    )
    class Meta(DeviceSerializer.Meta):
        fields = ("org", "sg", "user")

    def create(self, validated_data):
        template = DeviceTemplate.objects.filter(slug="generic-virtual-device-v1-0-0").first()
        user = validated_data.pop("user")
        validated_data.update({"template": template, "created_by": user, "claimed_by": user})
        return super().create(validated_data)
