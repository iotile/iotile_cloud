from rest_framework import serializers

from apps.devicetemplate.models import DeviceTemplate
from apps.sensorgraph.models import SensorGraph
from apps.physicaldevice.serializers import DeviceSerializer
from .models import *


class DeploymentRequestSerializer(serializers.ModelSerializer):
    script = serializers.SlugRelatedField(
        queryset=DeviceScript.objects.all(),
        slug_field='slug'
     )
    org = serializers.SlugRelatedField(
        queryset=Org.objects.all(),
        slug_field='slug'
     )
    fleet = serializers.SlugRelatedField(
        queryset=Fleet.objects.all(),
        slug_field='slug',
        required=False
     )
    class Meta:
        model = DeploymentRequest
        fields = ('id', 'script', 'selection_criteria', 'org', 'fleet',
                  'released_on', 'completed_on', )
        read_only_fields = ('created_on', 'completed_on', 'released_on')


class DeploymentActionSerializer(serializers.ModelSerializer):
    device = serializers.SlugRelatedField(
        queryset=Device.objects.all(),
        slug_field='slug'
     )
    class Meta:
        model = DeploymentAction
        fields = ('id', 'deployment', 'device', 'created_on',
                  'last_attempt_on', 'attempt_successful', 'device_confirmation', 'log')
        read_only_fields = ('created_on', 'device_confirmation',)


class DeploymentActionReadOnlySerializer(serializers.ModelSerializer):
    class Meta:
        model = DeploymentAction
        fields = ('id', 'deployment', 'last_attempt_on', 'attempt_successful', 'device_confirmation',)


class DeviceVersionAttributeSerializer(serializers.ModelSerializer):
    device = serializers.SlugRelatedField(
        queryset=Device.objects.all(),
        slug_field='slug'
    )
    class Meta:
        model = DeviceVersionAttribute
        fields = ( 'device', 'type', 'tag', 'version', 'major_version', 'minor_version',
                   'streamer_local_id', 'updated_ts', 'created_on')
        read_only_fields = ('created_on', 'version')
        extra_kwargs = {
            'major_version': {'write_only': True},
            'minor_version': {'write_only': True},
        }


class DeviceVersionAttributeReadOnlySerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceVersionAttribute
        fields = ('type', 'tag', 'version', 'streamer_local_id', 'updated_ts',)


class DeploymentRequestDeviceListSerializer(DeviceSerializer):
    template = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug'
     )
    sg = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug'
     )
    versions = serializers.SerializerMethodField()

    class Meta(DeviceSerializer.Meta):
        fields = (
            'id',
            'slug',
            'sg',
            'template',
            'versions',
        )
        read_only_fields = (
            'id',
            'slug',
            'sg',
            'template',
        )

    def get_versions(self, obj):
        # Only return the last update for each type of version
        qs = DeviceVersionAttribute.objects.current_device_version_qs(device=obj)
        serializer = DeviceVersionAttributeReadOnlySerializer(qs, many=True)
        return serializer.data


class DeploymentDeviceInfoSerializer(DeploymentRequestDeviceListSerializer):
    deployments = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()

    class Meta(DeploymentRequestDeviceListSerializer.Meta):
        fields = ('slug', 'template', 'sg', 'deployments', 'actions', 'versions')

    def get_deployments(self, obj):
        qs = DeploymentRequest.objects.device_deployments_qs(obj, released=True)
        serializer = DeploymentRequestSerializer(qs, many=True)
        return serializer.data

    def get_actions(self, obj):
        qs = DeploymentAction.objects.filter(device=obj).order_by('last_attempt_on')
        serializer = DeploymentActionReadOnlySerializer(qs, many=True)
        return serializer.data


