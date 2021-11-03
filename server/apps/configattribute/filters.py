from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.db.models import Q

import django_filters

from .models import *


class ConfigAttributeNameFilter(django_filters.rest_framework.FilterSet):
    name_q = django_filters.CharFilter(method='filter_by_search', label='Search for names that contain this string')
    tag = django_filters.CharFilter(method='filter_by_tag', label='Search by tag')
    class Meta:
        model = ConfigAttributeName
        fields = ['name']

    def filter_by_search(self, queryset, name, value):
        return ConfigAttributeName.objects.filter(name__icontains=value)

    def filter_by_tag(self, queryset, name, value):
        return ConfigAttributeName.objects.filter(tags__contains=[value])


class ConfigAttributeFilter(django_filters.rest_framework.FilterSet):
    name_q = django_filters.CharFilter(method='filter_by_search', label='Search for names that contain this string')
    target = django_filters.CharFilter(method='filter_by_target', required=True,
                                       label='Required argument for target slug for which attributes are assigned to')
    class Meta:
        model = ConfigAttribute
        fields = []

    def filter_by_search(self, queryset, name, value):
        names_qs = ConfigAttributeName.objects.filter(name__icontains=value)
        q = Q(name__in=names_qs)

        return queryset.filter(q)

    def filter_by_target(self, queryset, name, value):
        target_slug = value
        if target_slug:
            obj_type, target = get_object_by_slug(target_slug)
            if target:
                if target.has_access(self.request.user):
                    return queryset.filter(target=target_slug)

        return ConfigAttribute.objects.none()



