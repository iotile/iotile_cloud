from django.contrib.auth import get_user_model

from rest_framework import serializers

from apps.org.models import Org
from apps.physicaldevice.models import Device
from apps.projecttemplate.models import ProjectTemplate

from .models import Project

user_model = get_user_model()


class ProjectSerializer(serializers.ModelSerializer):
    org = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Org.objects.all()
    )
    project_template = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=ProjectTemplate.objects.all(),
        required=False
    )
    created_by = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    gid = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ('id', 'name', 'slug', 'gid', 'org', 'about', 'project_template',
                  'created_on', 'created_by')
        read_only_fields = ('created_on', 'slug', 'gid')
        extra_kwargs = {'device_slugs': {'write_only': True}}

    def get_gid(self, obj):
        return obj.formatted_gid


class ProjectFromTemplateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=50)
    org = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Org.objects.all()
    )
    device = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Device.objects.all(),
        required=False
    )


class ProjectExtraInfoSerializer(ProjectSerializer):
    counts = serializers.SerializerMethodField()
    class Meta:
        model = Project
        fields = ('id', 'name', 'slug', 'gid', 'org', 'about', 'project_template', 'counts',
                  'created_on', 'created_by')
        read_only_fields = ('created_on', 'slug', 'gid', 'counts',)

    def get_counts(self, obj):
        return {
            'active_devices': obj.devices.filter(active=True).count(),
            'inactive_devices': obj.devices.filter(active=False).count(),
            'variables': obj.variables.count(),
            'streams': obj.streamids.filter(block__isnull=True).count(),
        }
