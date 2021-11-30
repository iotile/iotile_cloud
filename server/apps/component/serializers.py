from rest_framework import serializers

from .models import *


class ComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Component
        fields = ('id', 'external_sku', 'internal_sku', 'slug', 'type', 'hw_tag', 'hw_name',
                  'major_version', 'minor_version', 'patch_version', 'version', 'description',
                  'created_on')
        read_only_fields = ('created_on', 'slug', )
        extra_kwargs = {
            'major_version': {'write_only': True},
            'minor_version': {'write_only': True},
            'patch_version': {'write_only': True},
        }


