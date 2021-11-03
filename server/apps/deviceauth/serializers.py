from rest_framework import serializers

from .models import DeviceKey


class DeviceKeyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceKey
        fields = ('slug', 'type', 'downloadable', 'secret')


class DeviceKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceKey
        fields = ["type", "secret"]
