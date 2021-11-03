from rest_framework import serializers

from .models import *


class DeviceLocationSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    target = serializers.CharField(source='target_slug', required=True)
    class Meta:
        model = DeviceLocation
        fields = ('id', 'timestamp', 'target', 'lat', 'lon', 'user')
