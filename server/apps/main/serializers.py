from rest_framework import serializers

from django.utils import timezone
from django.conf import settings
from apps.utils.timezone_utils import str_utc

class ServerInfoSerializer(serializers.Serializer):
    now = serializers.SerializerMethodField()
    stage = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    company = serializers.SerializerMethodField()

    def get_now(self, obj):
        return str_utc(timezone.now())

    def get_stage(self, obj):
        return getattr(settings, 'SERVER_TYPE')

    def get_name(self, obj):
        return getattr(settings, 'SITE_NAME')

    def get_company(self, obj):
        return getattr(settings, 'COMPANY_NAME')
