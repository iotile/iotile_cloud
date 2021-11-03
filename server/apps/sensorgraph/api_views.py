import logging
from django.core.cache import caches
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404

import django_filters
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status, mixins

from apps.utils.rest.cached_views import cache_on_auth
from apps.utils.rest.permissions import IsStaffOrReadOnly, HasAuthAPIKeyNoOrg
from apps.property.serializers import GenericPropertyOrgTemplateSerializer

from apps.org.models import AuthAPIKey
from apps.utils.api_key_utils import get_org_slug_from_apikey

from .models import *
from .serializers import *

logger = logging.getLogger(__name__)


class APISensorGraphViewSet(viewsets.ModelViewSet):
    """
    TNot Documented. For Internal Use Only.
    """
    lookup_field = 'slug'
    queryset = SensorGraph.objects.none()
    serializer_class = SensorGraphSerializer
    filterset_fields = ('created_by', 'variable_templates', 'org__slug', 'slug')
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            permission_classes = [HasAuthAPIKeyNoOrg | IsStaffOrReadOnly]
        else:
            permission_classes = [IsStaffOrReadOnly]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        if self.request.user.is_staff and (self.request.GET.get('staff', '0') == '1'):
            qs = SensorGraph.objects.all()
        else:
            apikeyOrg = get_org_slug_from_apikey(self.request)
            if 'slug' in self.kwargs:
                # Allow even if not active if doing a Retrieve (single object)
                qs = SensorGraph.objects.filter(slug=self.kwargs['slug'])
            else:
                qs = SensorGraph.objects.filter(active=True)

        return qs.prefetch_related(
            'variable_templates', 'display_widget_templates', 'org_properties', 'org'
        )

    def perform_create(self, serializer):
        # Include the owner attribute directly, rather than from request data.
        instance = serializer.save(created_by=self.request.user)

    @method_decorator(cache_on_auth(60 * 15, key_prefix="api:sg"))
    def dispatch(self, *args, **kwargs):
        return super(APISensorGraphViewSet, self).dispatch(*args, **kwargs)

    @action(methods=['get', 'post'], detail=True)
    def property(self, request, slug=None):
        """
        POST: Create a new Property Template Enum Value.
        Payload :
        - value: (required) Str
        """
        obj = get_object_or_404(SensorGraph, slug=slug)
        if request.method == 'GET':
            org_slug = self.request.GET.get('org', None)
            if org_slug:
                org = get_object_or_404(Org, slug=org_slug)
                templates = obj.org_properties.filter(org=org)
            else:
                templates = obj.org_properties.filter(org=obj.org)
            page = self.paginate_queryset(templates)
            if page is not None:
                serializer = GenericPropertyOrgTemplateSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = GenericPropertyOrgTemplateSerializer(templates, many=True)
            return Response(serializer.data)
        elif request.method == 'POST':
            if self.request.user.is_admin:
                serializer = SensorGraphAddOrgTemplateSerializer(data=request.data)
                if serializer.is_valid():
                    template_id = serializer.validated_data['id']
                    template = get_object_or_404(GenericPropertyOrgTemplate, pk=template_id)
                    obj.org_properties.add(template)
                    return Response(serializer.data, status=status.HTTP_201_CREATED)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response('Illegal Method', status=status.HTTP_400_BAD_REQUEST)


class APIVariableTemplateViewSet(viewsets.ModelViewSet):
    """
    TNot Documented. For Internal Use Only.
    """
    lookup_field = 'id'
    queryset = VariableTemplate.objects.all()
    serializer_class = VariableTemplateSerializer
    permission_classes = [IsStaffOrReadOnly]
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    http_method_names = ['post', 'head', 'put', 'patch', 'options']

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        if 'id' in self.kwargs:
            qs = VariableTemplate.objects.filter(id=self.kwargs['id'])
        else:
            qs = VariableTemplate.objects.filter()

        return qs

    def perform_create(self, serializer):
        # Include the owner attribute directly, rather than from request data.
        instance = serializer.save(created_by=self.request.user)


class APIDisplayWidgetTemplateViewSet(viewsets.ModelViewSet):
    """
    TNot Documented. For Internal Use Only.
    """
    lookup_field = 'id'
    queryset = DisplayWidgetTemplate.objects.all()
    serializer_class = DisplayWidgetTemplateSerializer
    permission_classes = [IsStaffOrReadOnly]
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    http_method_names = ['post', 'head', 'put', 'patch', 'options']

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        if 'id' in self.kwargs:
            qs = DisplayWidgetTemplate.objects.filter(id=self.kwargs['id'])
        else:
            qs = DisplayWidgetTemplate.objects.filter()

        return qs

    def perform_create(self, serializer):
        # Include the owner attribute directly, rather than from request data.
        instance = serializer.save(created_by=self.request.user)
