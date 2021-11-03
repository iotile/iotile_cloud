from rest_framework import serializers

from .models import *


class DeviceS3FileSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    key = serializers.SerializerMethodField()
    class Meta:
        model = DeviceFile
        fields = ('url', 'key', 'type', 'tag', 'version',)

    def get_url(self, obj):
        if obj.file:
            return obj.file.url
        return None

    def get_key(self, obj):
        if obj.file:
            return obj.file.key
        return None


class DeviceFileSerializer(serializers.ModelSerializer):
    released_by = serializers.SlugRelatedField(
        queryset=Org.objects.filter(is_vendor=True),
        slug_field='slug'
     )
    class Meta:
        model = DeviceFile
        fields = ('slug', 'type', 'tag',
                  'major_version', 'minor_version', 'version', 'notes',
                  'created_on', 'released', 'released_by')
        read_only_fields = ('created_on', 'slug', 'version', )
        extra_kwargs = {
            'major_version': {'write_only': True},
            'minor_version': {'write_only': True},
        }
