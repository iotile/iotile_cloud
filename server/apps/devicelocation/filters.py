from django.db.models import Q

import django_filters

from apps.utils.objects.utils import get_object_by_slug
from .models import DeviceLocation

class DeviceLocationFilter(django_filters.rest_framework.FilterSet):
    target = django_filters.CharFilter(method='filter_by_target', required=True,
                                       label='Required argument for target slug for which attributes are assigned to')
    start = django_filters.IsoDateTimeFilter(field_name='timestamp', lookup_expr='gte')
    end = django_filters.IsoDateTimeFilter(field_name='timestamp', lookup_expr='lt')
    class Meta:
        model = DeviceLocation
        fields = ['target', 'timestamp']

    def filter_by_target(self, queryset, name, value):
        target_slug = value
        if target_slug:
            obj_type, target = get_object_by_slug(target_slug)
            if target:
                if target.org.has_permission(self.request.user, 'can_read_device_locations'):
                    qs = queryset.filter(target_slug=target_slug)
                    return qs

        return DeviceLocation.objects.none()


