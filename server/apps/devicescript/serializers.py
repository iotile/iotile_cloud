from rest_framework import serializers

from .models import *


class DeviceScriptFileSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    key = serializers.SerializerMethodField()
    class Meta:
        model = DeviceScript
        fields = ('name', 'url', 'key', 'major_version', 'minor_version', 'patch_version')

    def get_url(self, obj):
        if obj.file:
            return obj.file.url
        return None

    def get_key(self, obj):
        if obj.file:
            return obj.file.key
        return None


class DeviceScriptSerializer(serializers.ModelSerializer):
    org = serializers.SlugRelatedField(
        queryset=Org.objects.filter(is_vendor=True),
        slug_field='slug'
     )
    class Meta:
        model = DeviceScript
        fields = ('slug', 'gid', 'name', 'org',
                  'major_version', 'minor_version', 'patch_version', 'version',
                  'created_on', 'released', 'released_on')
        read_only_fields = ('created_on', 'slug', 'gid', 'version', 'released_on')
        extra_kwargs = {
            'major_version': {'write_only': True},
            'minor_version': {'write_only': True},
            'patch_version': {'write_only': True},
        }


class DeviceScriptReadOnlySerializer(serializers.ModelSerializer):
    org = serializers.SlugRelatedField(
        queryset=Org.objects.filter(is_vendor=True),
        slug_field='slug'
     )
    class Meta:
        model = DeviceScript
        fields = ('slug', 'gid', 'name', 'org', 'version', 'released', 'released_on')
        read_only_fields = ('created_on', 'version')

