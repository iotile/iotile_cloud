from rest_framework import serializers

from .models import *


class DeviceSlotSerializer(serializers.ModelSerializer):
    component = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Component.objects.all()
    )
    class Meta:
        model = DeviceSlot
        fields = ('number', 'component')


class DeviceSlotReadOnlySerializer(serializers.ModelSerializer):
    component = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug'
    )
    hw_tag = serializers.SerializerMethodField()
    class Meta:
        model = DeviceSlot
        fields = ('number', 'component', 'hw_tag')

    def get_hw_tag(self, obj):
        return obj.component.hw_tag


class DeviceTemplateSerializer(serializers.ModelSerializer):
    org = serializers.SlugRelatedField(
        queryset=Org.objects.filter(is_vendor=True),
        slug_field='slug'
     )
    slots = DeviceSlotReadOnlySerializer(
        many=True,
        read_only=True,
     )
    class Meta:
        model = DeviceTemplate
        fields = ('id', 'external_sku', 'internal_sku', 'family', 'slug', 'org',
                  'version', 'major_version', 'minor_version', 'patch_version',
                  'os_tag', 'os_version', 'os_major_version', 'os_minor_version',
                  'hw_tag', 'hw_version', 'hw_major_version',
                  'slots',
                  'created_on', 'released_on')
        read_only_fields = ('created_on', 'slug')
        extra_kwargs = {
            'major_version': {'write_only': True},
            'minor_version': {'write_only': True},
            'patch_version': {'write_only': True},
            'os_major_version': {'write_only': True},
            'os_minor_version': {'write_only': True},
            'hw_major_version': {'write_only': True},
        }
