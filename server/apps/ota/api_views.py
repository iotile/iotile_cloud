import json
import logging
from django.http import HttpResponse, Http404
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.db.models import Q

import django_filters

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework import mixins
from rest_framework import generics
from rest_framework.decorators import action
from rest_framework.response import Response

from drf_yasg.utils import no_body, swagger_auto_schema

from apps.utils.rest.permissions import IsStaffOrReadOnly
from apps.org.permissions import IsMemberOnly

from .models import *
from .serializers import *
from .filters import *
from .utils.selection import DeploymentDeviceSelectionHelper

logger = logging.getLogger(__name__)


class APIDeviceVersionViewSet(viewsets.ModelViewSet):
    """
    A Device Version Attribute represents a version for a given aspect of the device. Examples:

    * OS: Represents the FW version
    * APP: Represents the Sensor Graph Version, which represents the application and configuration of the given device

    """
    queryset = DeviceVersionAttribute.objects.none()
    serializer_class = DeviceVersionAttributeSerializer
    permission_classes = (IsAuthenticated,)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = DeviceVersionAttributeFilter

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        all = self.request.user.is_staff and (self.request.GET.get('staff', '0') == '1')
        if all:
            qs = DeviceVersionAttribute.objects.all()
        else:
            devices = Device.objects.user_device_qs(self.request.user)
            qs = DeviceVersionAttribute.objects.filter(device__in=devices)

        return qs.select_related('device',)

    def create(self, request, *args, **kwargs):
        """
        Staff Only.
        Updating Device Versions is not permitted for users
        """
        if request.user.is_staff and (request.GET.get('staff', '0') == '1'):
            return super(APIDeviceVersionViewSet, self).create(request, *args)
        return Response({'error': 'Restricted Access. Contact Arch'}, status=status.HTTP_403_FORBIDDEN)

    def update(self, request, *args, **kwargs):
        """
        Staff Only.
        Updating Device Versions is not permitted for users
        """
        if request.user.is_staff and (request.GET.get('staff', '0') == '1'):
            return super(APIDeviceVersionViewSet, self).update(request, *args)
        return Response({'error': 'Restricted Access. Contact Arch'}, status=status.HTTP_403_FORBIDDEN)

    def destroy(self, request, *args, **kwargs):
        """
        Staff Only.
        Deleting Device Versions is not permitted for users
        """
        if request.user.is_staff and (request.GET.get('staff', '0') == '1'):
            return super(APIDeviceVersionViewSet, self).destroy(request, *args)
        return Response({'error': 'Restricted Access. Contact Arch'}, status=status.HTTP_403_FORBIDDEN)


class APIDeploymentRequestViewSet(viewsets.ModelViewSet):
    """
    A Deployment Request represents instructions for a remote update.
    Deployment Request target a fleet of devices and use a selection criteria to narrow the application.
    """
    queryset = DeploymentRequest.objects.none()
    serializer_class = DeploymentRequestSerializer
    permission_classes = (IsAuthenticated, IsMemberOnly)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = DeploymentRequestFilter

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        if 'pk' in self.kwargs:
            # Users are allowed to access if they know the ID
            return DeploymentRequest.objects.all()

        all = self.request.user.is_staff and (self.request.GET.get('staff', '0') == '1')
        if all:
            qs = DeploymentRequest.objects.all()
        else:
            filters = 'fleet' in self.request.GET or 'org' in self.request.GET or 'scope' in self.request.GET
            if not filters:
                # Users are not allowed to list all deployments without a filter
                return DeploymentRequest.objects.none()
            # Assumes further filtering is implemented on DeploymentRequestFilter
            # But only display released (and not completed) deployments
            qs = DeploymentRequest.objects.released_and_active_qs()

        return qs.select_related('script', 'org')

    def perform_create(self, serializer):
        org = serializer.validated_data['org']
        if not org.has_permission(self.request.user, 'can_manage_ota'):
            raise PermissionDenied('User has no permissions to manage devices')

        # Include the owner attribute directly, rather than from request data.
        serializer.save(created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        """
        Staff Only.
        Deleting Actions is not permitted for users
        """
        if request.user.is_staff and (request.GET.get('staff', '0') == '1'):
            return super(APIDeploymentRequestViewSet, self).destroy(request, *args)
        obj = self.get_object()
        if obj.has_write_access(self.request.user):
            return super(APIDeploymentRequestViewSet, self).destroy(request, *args)
        return Response({'error': 'Restricted Access. Contact Arch'}, status=status.HTTP_403_FORBIDDEN)

    @swagger_auto_schema(
        operation_id='Deployment Request - Devices',
        responses={
            200: DeploymentRequestDeviceListSerializer(many=True),
        }
    )
    @action(methods=['get'], detail=True)
    def devices(self, request, pk=None):
        """
        List of devices that are affected by this Deployment Request (based on what the cloud knows)
        """
        obj = self.get_object()
        helper = DeploymentDeviceSelectionHelper(obj)
        device_qs = helper.affected_devices_qs()
        page = self.paginate_queryset(device_qs)
        if page is not None:
            serializer = DeploymentRequestDeviceListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = DeploymentRequestDeviceListSerializer(device_qs, many=True)
        return Response(serializer.data)


class APIDeploymentActionViewSet(viewsets.ModelViewSet):
    """
    A Deployment Action represents an attempt to update a given device given a Deployment Request
    """
    queryset = DeploymentAction.objects.none()
    serializer_class = DeploymentActionSerializer
    permission_classes = (IsAuthenticated, IsMemberOnly)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = DeploymentActionFilter

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        if 'pk' in self.kwargs:
            # Users are allowed to access if they know the ID
            return DeploymentAction.objects.all()

        all = self.request.user.is_staff and (self.request.GET.get('staff', '0') == '1')
        if all:
            qs = DeploymentAction.objects.all()
        else:
            filters = 'request' in self.request.GET or 'device' in self.request.GET
            if not filters:
                # Users are not allowed to list all actions without a filter
                return DeploymentAction.objects.none()
            # Additonal filtering will be done by DeploymentActionFilter
            qs = DeploymentAction.objects.all()

        return qs.select_related('device')

    def perform_create(self, serializer):
        """
        Create a new Deployment Action.
        Check that user has access to deployment and device
        """
        # Make sure name won't produce duplicate slug
        deployment_request = serializer.validated_data['deployment']
        if not deployment_request.has_access(self.request.user):
            raise PermissionDenied('User has no access to deployment')
        device = serializer.validated_data['device']
        if not device.has_access(self.request.user):
            raise PermissionDenied('User has no access to device')

        serializer.save()

    def update(self, request, *args, **kwargs):
        """
        Staff Only.
        Updating Actions is not permitted for users
        """

        if request.user.is_staff and (request.GET.get('staff', '0') == '1'):
            return super(APIDeploymentActionViewSet, self).update(request, *args, **kwargs)
        return Response({'error': 'Restricted Access. Contact Arch'}, status=status.HTTP_403_FORBIDDEN)

    def destroy(self, request, *args, **kwargs):
        """
        Staff Only.
        Deleting Actions is not permitted for users
        """
        if request.user.is_staff and (request.GET.get('staff', '0') == '1'):
            return super(APIDeploymentActionViewSet, self).destroy(request, *args)
        return Response({'error': 'Restricted Access. Contact Arch'}, status=status.HTTP_403_FORBIDDEN)


class APIDeploymentDeviceInfoViewSet(generics.RetrieveAPIView):
    """
    Returns Device Management (OTA) related information related to this device.
    Includes:

    * list of Deployment Requests associated to this device
    * list of Deployment Actions done by any agent (i.e. mobile, gateway)
    * list of current associated Version Attributes
    """
    lookup_field = 'slug'
    queryset = Device.objects.filter(project__isnull=False, active=True)
    serializer_class = DeploymentDeviceInfoSerializer
    permission_classes = (IsAuthenticated, IsMemberOnly)

    def get_object(self):
        """
        Get object based on given slug

        Returns: Device Version and Deployment Info

        """
        slug = self.kwargs['slug']

        # TODO: Should we only allow access to the device in question when using a-jwt?
        if self.request.auth and isinstance(self.request.auth, dict):
            if 'device' in self.request.auth:
                jwt_device = self.request.auth['device']
                if jwt_device != slug:
                    logger.warning('a-jwt for device {0} accessing device {1}'.format(jwt_device, slug))

        dev = get_object_or_404(Device, slug=slug)

        if dev.active and dev.has_access(self.request.user):
            return dev

        raise PermissionDenied('User has no access to Device')
