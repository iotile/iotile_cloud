import json
import logging
from django.http import HttpResponse, Http404
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.conf import settings

import django_filters
from rest_framework import viewsets
from rest_framework import status
from rest_framework import exceptions as drf_exceptions
from rest_framework.decorators import action
from rest_framework.response import Response

from drf_yasg.utils import swagger_auto_schema


from apps.property.mixins import GeneralPropertyMixin
from apps.org.permissions import IsMemberOnly
from apps.utils.uuid_utils import validate_uuid

from .utils import create_project_from_device
from .models import *
from .serializers import ProjectSerializer, ProjectFromTemplateSerializer, ProjectExtraInfoSerializer

logger = logging.getLogger(__name__)


class ProjectApiFilter(django_filters.rest_framework.FilterSet):
    org__slug = django_filters.CharFilter(method='filter_by_org')
    org = django_filters.CharFilter(method='filter_by_org')
    property = django_filters.CharFilter(method='filter_by_property')
    class Meta:
        model = Project
        fields = ['org', 'slug', 'created_by', 'name']

    def filter_by_org(self, queryset, name, value):
        org = get_object_or_404(Org, slug=value)
        return queryset.filter(org=org)

    def filter_by_property(self, queryset, name, value):
        parts = value.split('__')
        if len(parts) == 1:
            properties = GenericProperty.objects.filter(target__istartswith='p--', name=parts[0])
            slugs = [p.target for p in properties]
            return queryset.filter(slug__in=slugs)
        if len(parts) == 2:
            properties = GenericProperty.objects.filter(target__istartswith='p--', name=parts[0], str_value=parts[1])
            slugs = [p.target for p in properties]
            return queryset.filter(slug__in=slugs)
        return queryset


class APIProjectViewSet(viewsets.ModelViewSet, GeneralPropertyMixin):
    """
    Get a list of all Projects the authenticated user has access to.
    Projects are a way to manage and view a set of related Devices, such as all
    the Devices in a particular area, or all Devices measuring certain variables.
    User Accounts can access all Projects within Orgs they belong to.

    create: Creates an empty Project with no Devices.

    list: Get the list of Projects you have access to.

    retrieve: Get the project with the given ID (ID is in UUID format)

    """
    queryset = Project.objects.none()
    serializer_class = ProjectSerializer
    permission_classes = (IsMemberOnly,)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = ProjectApiFilter

    def get_object(self):
        id = self.kwargs['pk']
        if not validate_uuid(id):
            raise drf_exceptions.ValidationError('Project ID must be a UUID')

        return super(APIProjectViewSet, self).get_object()

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        all = self.request.user.is_staff and (self.request.GET.get('staff', '0') == '1')
        if all:
            qs = Project.objects.all()
        else:
            qs =Project.objects.user_project_qs(self.request.user)

        return qs.select_related('org', 'created_by', 'project_template')

    def perform_create(self, serializer):
        # Include the owner attribute directly, rather than from request data.
        org = serializer.validated_data['org']
        if not org.has_permission(self.request.user, 'can_manage_org_and_projects'):
            raise drf_exceptions.PermissionDenied('Access Denied due to lack of sufficient permissions')

        if 'project_template' in serializer.validated_data and serializer.validated_data['project_template']:
            project_template = serializer.validated_data['project_template']
        else:
            project_template = ProjectTemplate.objects.filter(name='Default Template').last()

        serializer.save(created_by=self.request.user, project_template=project_template)

    @swagger_auto_schema(
        method='get',
        responses={
            200: ProjectExtraInfoSerializer(many=False)
        }
    )
    @action(methods=['get'], detail=True)
    def extra(self, request, *args, **kwargs):
        """
         Return project details, including device, stream and variable counts
        """
        org = self.get_object()
        serializer = ProjectExtraInfoSerializer(org, context={"request": request})

        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(methods=['post'], detail=False)
    def new(self, request):
        """
        Create a new Project given a Device ID. Proper permissions required
        
        Project defaults such as display properties will be determined by the Device
        type. Projects must be created within an Org.
        """
        serializer = ProjectFromTemplateSerializer(data=request.data)
        if serializer.is_valid():
            name = serializer.validated_data['name']
            org = serializer.validated_data['org']
            if not org.has_permission(self.request.user, 'can_manage_org_and_projects'):
                raise drf_exceptions.PermissionDenied('Access Denied due to lack of sufficient permissions')

            if 'device' in serializer.validated_data:
                device = serializer.validated_data['device']
                if device:
                    logger.info('Looking for project defaults based on {}'.format(device))

                    project, msg = create_project_from_device(
                        device=device,
                        created_by=self.request.user,
                        project_name=name,
                        org=org
                    )
                    if project:
                        return Response({'id': str(project.id)}, status=status.HTTP_201_CREATED)
                    else:
                        return Response(msg, status=status.HTTP_400_BAD_REQUEST)
                raise drf_exceptions.ValidationError('Illegal device')
            else:
                project = Project.objects.create(created_by=self.request.user, name=name, org=org)
                return Response({'id': str(project.id)}, status=status.HTTP_201_CREATED)

        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        """Fully update a given project (ID is in UUID format). Proper permissions required."""
        project = self.get_object()
        org = project.org
        if not org.has_permission(request.user, 'can_manage_org_and_projects'):
            raise drf_exceptions.PermissionDenied('Access Denied due to lack of sufficient permissions')

        return super(APIProjectViewSet, self).update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Partial update a given project (ID is in UUID format). Proper permissions required """
        project = self.get_object()
        org = project.org
        if not org.has_permission(request.user, 'can_manage_org_and_projects'):
            raise drf_exceptions.PermissionDenied('Access Denied due to lack of sufficient permissions')

        return super(APIProjectViewSet, self).partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Staff Only.
        
        Delete a Project. If a Project is deleted, Devices associated with that
        Project are not automatically deleted.
        """
        if not request.user.is_staff:
            return Response({'error': 'Restricted Access. Contact Arch'}, status=status.HTTP_400_BAD_REQUEST)
        return super(APIProjectViewSet, self).destroy(request, args)
