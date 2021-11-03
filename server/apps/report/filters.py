from django.shortcuts import get_object_or_404

import django_filters

from apps.org.models import Org
from .models import GeneratedUserReport

class GeneratedUserReportApiFilter(django_filters.rest_framework.FilterSet):
    org = django_filters.CharFilter(method='filter_by_org')
    class Meta:
        model = GeneratedUserReport
        fields = ['org', 'source_ref', 'status', 'created_by', ]

    def filter_by_org(self, queryset, name, value):
        org = get_object_or_404(Org, slug=value)
        return queryset.filter(org=org)

