import django_filters
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from apps.utils.objects.utils import get_object_by_slug

from .models import *

class DeploymentRequestFilter(django_filters.rest_framework.FilterSet):
    fleet = django_filters.CharFilter(method='filter_by_fleet')
    org = django_filters.CharFilter(method='filter_by_org')
    scope = django_filters.CharFilter(method='filter_by_scope')
    class Meta:
        model = DeploymentRequest
        fields = ['fleet', 'org']

    def filter_by_fleet(self, queryset, name, value):
        q = Q()
        slugs = value.split(',')
        for slug in slugs:
            fleet = get_object_or_404(Fleet, slug=slug)
            if fleet.has_access(self.request.user):
                q = q | Q(fleet=fleet)
            else:
                raise PermissionDenied

        return queryset.filter(q)

    def filter_by_org(self, queryset, name, value):
        q = Q()
        slugs = value.split(',')
        for slug in slugs:
            org = get_object_or_404(Org, slug=slug)
            if org.is_vendor or org.has_access(self.request.user):
                q = q | Q(org=org)
            else:
                raise PermissionDenied

        return queryset.filter(q)

    def filter_by_scope(self, queryset, name, value):
        """
        Scope can be 'global', a fleet slug, or an Org slug
        - global: Only includes vendor deployments
        - org: Includes Org deployments (no fleet) and vendor deployments
        - fleet: Includes Fleet, Org and vendor deployments
        """
        vendors = Org.objects.filter(is_vendor=True)
        if value == 'global':
            return queryset.filter(Q(fleet__isnull=True, org__in=vendors))
        n, o = get_object_by_slug(value)
        if n == 'fleet':
            if o.has_access(self.request.user):
                # Any deployment to this fleet, any other deployments to Org (no fleet) or global vendor deployments
                q = Q(fleet=o) | \
                    Q(fleet__isnull=True, org=o.org) | \
                    Q(fleet__isnull=True, org__in=vendors)
                return queryset.filter(q)
        else:
            org = get_object_or_404(Org, slug=value)
            if org.has_access(self.request.user):
                # Any deployment affecting vendor, this Org, or fleet under this Org
                org_fleets = Fleet.objects.filter(org=org)
                q = Q(org=org) | \
                    Q(fleet__in=org_fleets, org__in=vendors) | \
                    Q(fleet__isnull=True, org__in=vendors)
                return queryset.filter(q)
        return DeploymentRequest.objects.none()


class DeploymentActionFilter(django_filters.rest_framework.FilterSet):
    request = django_filters.CharFilter(method='filter_by_request')
    device = django_filters.CharFilter(method='filter_by_device')
    class Meta:
        model = DeploymentAction
        fields = ['request',]

    def filter_by_request(self, queryset, name, value):
        # Only filter by fleet if fleet exists and user has access
        deployment_request = get_object_or_404(DeploymentRequest, pk=value)
        if deployment_request.has_access(self.request.user):
            return queryset.filter(deployment=deployment_request)
        else:
            raise PermissionDenied

    def filter_by_device(self, queryset, name, value):
        # Only filter by fleet if fleet exists and user has access
        device = get_object_or_404(Device, slug=value)
        if device.has_access(self.request.user):
            return queryset.filter(device=device)
        else:
            raise PermissionDenied


class DeviceVersionAttributeFilter(django_filters.rest_framework.FilterSet):
    device = django_filters.CharFilter(method='filter_by_device')
    latest = django_filters.BooleanFilter(method='filter_by_latest')
    class Meta:
        model = DeviceVersionAttribute
        fields = ['device', 'type', 'latest']

    def filter_by_device(self, queryset, name, value):
        # Only filter by fleet if fleet exists and user has access
        device = get_object_or_404(Device, slug=value)
        if device.has_access(self.request.user):
            return queryset.filter(device=device)
        else:
            raise PermissionDenied

    def filter_by_latest(self, queryset, name, value):
        return queryset.order_by('type', '-updated_ts').distinct('type')
