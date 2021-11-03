import logging

import django_filters
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema
from iotile_cloud.utils.gid import IOTileProjectSlug
from rest_framework import exceptions as drf_exceptions
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.org.permissions import IsMemberOnly
from apps.utils.uuid_utils import validate_uuid

from .models import *
from .serializers import StreamAliasSerializer, StreamAliasTapSerializer

# Get an instance of a logger
logger = logging.getLogger(__name__)


def check_permissions(user, org):
    """
    Check that the user can manage stream aliases of the org
    Raise a PermissionDenied exception if the user doesn't have the permissions
    """
    if org and not org.has_permission(user, 'can_manage_stream_aliases'):
        raise drf_exceptions.PermissionDenied('Access Denied due to lack of sufficient permissions')


class StreamAliasApiFilter(django_filters.rest_framework.FilterSet):
    org = django_filters.CharFilter(method='filter_by_org')

    class Meta:
        model = StreamAlias
        fields = ['org']

    def filter_by_org(self, queryset, name, value):
        org = get_object_or_404(Org, slug=value)
        return queryset.filter(org=org)


class APIStreamAliasViewSet(viewsets.ModelViewSet):
    """
    Get a list of all Stream Aliases the authenticated user has access to.
    Stream Aliases are a way to dynamically build virtual streams with sections from
    different physical streams. They are basically a list of Stream Alias Taps.
    User Account can access all Stream Aliases within Orgs they belong to.

    create: Creates an empty Stream Alias.

    list: Get the list of Stream Aliases you have access to.

    retrieve: Get the Stream Alias with the given slug.
    """
    lookup_field = 'slug'
    queryset = StreamAlias.objects.none()
    serializer_class = StreamAliasSerializer
    permission_classes = (IsMemberOnly,)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = StreamAliasApiFilter
    search_fields = ('name',)

    def get_object(self):
        """
        Get object based on given slug.

        Returns: Stream Alias if it exists
        """
        alias = super(APIStreamAliasViewSet, self).get_object()
        check_permissions(self.request.user, alias.org)
        return alias

    def get_queryset(self):
        """
        Stream Aliases the user has access to.
        """
        if self.request.user.is_staff and (self.request.GET.get('staff', '0') == '1'):
            qs = StreamAlias.objects.all()
        else:
            qs = StreamAlias.objects.user_streamalias_qs(self.request.user)

        return qs.select_related('org', 'created_by')

    def perform_create(self, serializer):
        """
        Create a Stream Alias. Proper permissions required.
        """
        org = serializer.validated_data['org']
        # Check if permission is OK for new Org
        check_permissions(self.request.user, org)
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        """
        Update a Stream Alias. Proper permissions required.
        """
        org = serializer.validated_data.get('org')
        # Check if permission is OK for new Org
        check_permissions(self.request.user, org)
        serializer.save()


class StreamAliasTapApiFilter(django_filters.rest_framework.FilterSet):
    target = django_filters.CharFilter(method='filter_by_alias')

    class Meta:
        model = StreamAliasTap
        fields = ['target']

    def filter_by_alias(self, queryset, name, value):
        alias = get_object_or_404(StreamAlias, slug=value)
        return queryset.filter(alias=alias)


class APIStreamAliasTapViewSet(viewsets.ModelViewSet):
    """
    Stream Alias Taps are timestamped pointers to physical streams. A list of
    Stream Alias Taps can be used to construct a virtual stream from different data streams.
    User Account can access or manage Stream Alias Taps for Stream Aliases it can access or manage.

    create: Creates a Stream Alias Tap.

    list: Get the list of Stream Alias Taps for a given Stream Alias.

    retrieve: Get details of a Stream Alias Tap with the given id.
    """
    queryset = StreamAliasTap.objects.none()
    serializer_class = StreamAliasTapSerializer
    permission_classes = (IsMemberOnly,)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = StreamAliasTapApiFilter

    def get_object(self):
        """
        Get object based on given id.

        Returns: Stream Alias Tap if it exists
        """
        tap = super(APIStreamAliasTapViewSet, self).get_object()
        check_permissions(self.request.user, tap.alias.org)
        return tap

    def get_queryset(self):
        """
        Stream Alias Taps the user has access to.
        """
        if self.request.user.is_staff and (self.request.GET.get('staff', '0') == '1'):
            qs = StreamAliasTap.objects.all()
        else:
            qs = StreamAliasTap.objects.user_streamaliastap_qs(self.request.user)

        return qs.select_related('alias', 'stream', 'created_by')

    def perform_create(self, serializer):
        """
        Create a Stream Alias Tap. Proper permissions required.
        """
        alias = serializer.validated_data['alias']
        # Check if permission is OK for new Org
        check_permissions(self.request.user, alias.org)
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        """
        Update a Stream Alias Tap. Proper permissions required.
        """
        alias = serializer.validated_data.get('alias')
        if alias:
            # Check if permission is OK for new Org
            check_permissions(self.request.user, alias.org)
        serializer.save()
