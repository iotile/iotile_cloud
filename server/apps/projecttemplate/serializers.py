from rest_framework import serializers

from .models import *


class ProjectTemplateSerializer(serializers.ModelSerializer):
    org = serializers.SlugRelatedField(
        queryset=Org.objects.filter(is_vendor=True),
        slug_field='slug'
     )
    class Meta:
        model = ProjectTemplate
        fields = ('id', 'name', 'slug', 'org', 'version',  'extra_data',
                  'major_version', 'minor_version', 'patch_version',
                  'created_on', )
        read_only_fields = ('created_on', 'slug', 'version')
        extra_kwargs = {
            'major_version': {'write_only': True},
            'minor_version': {'write_only': True},
            'patch_version': {'write_only': True},
        }

    def validate_extra_data(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('extra_data must be a valid dictionary object')
        return value

