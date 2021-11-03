import json
import logging
from django.http import HttpResponse, Http404
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.db import IntegrityError
from django.core.paginator import Paginator
from django.db.models import Q

import django_filters
from rest_framework import viewsets
from rest_framework import mixins
from rest_framework import status
from rest_framework import filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotAcceptable, NotFound

from drf_yasg import openapi
from drf_yasg.utils import no_body, swagger_auto_schema

from apps.utils.rest.custom_serializers import MultiSerializerViewSetMixin
from apps.org.models import OrgMembership
from apps.utils.objects.utils import get_object_by_slug

from .models import *
from .serializers import *

logger = logging.getLogger(__name__)


# filterset_fields = ('created_by', 'project', 'org__slug', 'device__slug', 'variable')
class PropertyTemplateFilter(django_filters.rest_framework.FilterSet):
    org = django_filters.CharFilter(method='filter_by_org')
    class Meta:
        model = GenericPropertyOrgTemplate
        fields = ['org', 'name']

    def filter_by_org(self, queryset, name, value):
        org = get_object_or_404(Org, slug=value)
        return queryset.filter(org=org)


class APIPropertyTemplateViewSet(viewsets.ModelViewSet):
    """
    A Property Template is used to define a Property requirement in a device page.
    The Template is used by the Property Settings page to know what to present to users.
    What should the default be? What type of property should be created, etc.
    All property templates are associated to a given Organization, so each Organization
    can have different Properties

    list: Get list of property templates

    create: Create a new Property Template

    """
    queryset = GenericPropertyOrgTemplate.objects.none()
    serializer_class = GenericPropertyOrgTemplateSerializer
    permission_classes = (IsAuthenticated,)
    filterset_class = PropertyTemplateFilter
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)

    def _user_property_template_qs(self, user):
        membership = OrgMembership.objects.filter(user__id=user.id).select_related('org')
        orgs = Org.objects.filter(id__in=[m.org_id for m in membership])

        return GenericPropertyOrgTemplate.objects.filter(org__in=orgs).select_related('org', 'created_by')

    def get_queryset(self):
        """
        This view should return a list of all records if staff
        or all records the user has access to if not
        """
        if self.request.user.is_staff and self.request.GET.get('staff', ''):
            qs =  GenericPropertyOrgTemplate.objects.all()
        else:
            qs =  self._user_property_template_qs(self.request.user)

        return qs.prefetch_related('enums')

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)

    @action(methods=['get', 'post', 'delete'], detail=True)
    def enum(self, request, pk=None):
        """
        POST: Create a new Property Template Enum Value.
        Payload :
        - value: (required) Str
        """
        obj = self.get_object()
        if request.method == 'GET':
            enums = obj.enums.all()
            page = self.paginate_queryset(enums)
            if page is not None:
                serializer = GenericPropertyOrgEnumSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = GenericPropertyOrgEnumSerializer(enums, many=True)
            return Response(serializer.data)
        elif request.method == 'POST':
            serializer = GenericPropertyOrgEnumSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(created_by=self.request.user, org=obj.org, template=obj)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        elif request.method == 'DELETE':
            serializer = GenericPropertyOrgEnumSerializer(data=request.data)
            if serializer.is_valid():
                template = self.get_object()
                try:
                    enum = template.enums.get(value=request.data['value'])
                except GenericPropertyOrgEnum.DoesNotExist:
                    return Response({'error': 'Enum Value not found in Property Template'}, status=status.HTTP_404_NOT_FOUND)

                enum.delete()
                return Response({}, status=status.HTTP_204_NO_CONTENT)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response('Illegal Method', status=status.HTTP_400_BAD_REQUEST)


class APIGenericPropertyViewSet(MultiSerializerViewSetMixin, viewsets.ModelViewSet):
    """
    A Property can be used to store metadata in the form of name=value pairs to any of the supported targets:

    * Device Slugs
    * DataBlock Slugs
    * Project Slugs

    """
    queryset = GenericProperty.objects.none()
    serializer_class = GenericPropertyReadOnlySerializer
    serializer_action_classes = {
        'create': GenericPropertyWriteOnlySerializer,
        'update': GenericPropertyWriteOnlySerializer,
        'partial_update': GenericPropertyWriteOnlySerializer,
        'list': GenericPropertyReadOnlySerializer,
        'retrieve': GenericPropertyReadOnlySerializer,
    }
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        """
        Get object based on given slug. prepend '0000' as needed to
        properly format the device gid='d--0000-0000-0000-0001'

        Returns: Device if it exist

        """
        property = super(APIGenericPropertyViewSet, self).get_object()

        target = property.obj
        if not target.has_access(self.request.user):
            raise PermissionDenied

        return property

    def get_queryset(self):
        """
        This view should return a list of all records if staff
        or all records the user has access to if not
        """
        slug = self.request.GET.get('target', None)
        if slug:
            elements = slug.split('--')
            if elements[0] in ['p', 'd', 'b']:
                name, obj = get_object_by_slug(slug)
                if obj and obj.has_access(self.request.user):
                    return GenericProperty.objects.filter(target=slug)
                raise PermissionDenied
        elif 'pk' in self.kwargs:
            return GenericProperty.objects.all()

        raise NotAcceptable('target argument (e.g. target=d--0000-0000-0000-1234) is required')

    def perform_create(self, serializer):
        target = serializer.validated_data['target']
        name, obj = get_object_by_slug(target)
        if not obj.has_access(self.request.user):
            raise PermissionDenied

        instance = serializer.save(created_by=self.request.user)

    @swagger_auto_schema(
        responses={
            200: GenericPropertyReadOnlySerializer(many=True),
        },
        manual_parameters=[
            openapi.Parameter(
                name='target',
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description='Slug of either a device, data block or project',
                required=True
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        """
        List Properties
        """
        return super(APIGenericPropertyViewSet, self).list(request)

    @swagger_auto_schema(
        responses={
            200: GenericPropertyReadOnlySerializer(many=False),
        }
    )
    def retrieve(self, request, *args, **kwargs):
        """
        Get one property
        """
        return super(APIGenericPropertyViewSet, self).retrieve(request)

    @swagger_auto_schema(
        request_body=GenericPropertyWriteOnlySerializer,
        responses={
            201: GenericPropertyReadOnlySerializer(many=False),
        }
    )
    def create(self, request, *args, **kwargs):
        """
        Create new Property
        """
        return super(APIGenericPropertyViewSet, self).create(request)

    @swagger_auto_schema(
        request_body=GenericPropertyWriteOnlySerializer,
        responses={
            201: GenericPropertyReadOnlySerializer(many=False),
        }
    )
    def update(self, request, *args, **kwargs):
        """
        Edit property
        """
        return super(APIGenericPropertyViewSet, self).update(request, *args, **kwargs)

    @swagger_auto_schema(
        request_body=GenericPropertyWriteOnlySerializer,
        responses={
            201: GenericPropertyReadOnlySerializer(many=False),
        }
    )
    def partial_update(self, request, *args, **kwargs):
        """
        Edit property
        """
        return super(APIGenericPropertyViewSet, self).partial_update(request, *args, **kwargs)

    @swagger_auto_schema(
        responses={
            204: 'No response',
        }
    )
    def destroy(self, request, *args, **kwargs):
        """
        Delete property
        """
        return super(APIGenericPropertyViewSet, self).destroy(request, *args)

