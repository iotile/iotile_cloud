from rest_framework import serializers

from django.utils import timezone
from apps.utils.timezone_utils import str_utc

from apps.staff.dbstats import DbStats

class DbStatsSerializer(serializers.Serializer):
    now = serializers.SerializerMethodField()
    days = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()

    def get_now(self, obj):
        return str_utc(timezone.now())

    def get_days(self, obj):
        request = obj
        return request.GET.get('days', 'all')

    def get_stats(self, obj):
        request = obj
        days = request.GET.get('days', None)
        s = DbStats()
        if days:
            s.day_stats(int(days))
        else:
            s.compute_stats()
        return s.stats
