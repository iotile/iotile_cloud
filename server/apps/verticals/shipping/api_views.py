import logging

from django.shortcuts import get_object_or_404

from drf_yasg.utils import swagger_auto_schema
from rest_framework import exceptions as drf_exceptions
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from iotile_cloud.utils.gid import IOTileBlockSlug, IOTileDeviceSlug, IOTileStreamSlug

from apps.datablock.models import DataBlock
from apps.org.models import Org
from apps.org.permissions import IsMemberOnly
from apps.physicaldevice.models import Device
from apps.physicaldevice.serializers import DeviceSerializer
from apps.project.models import Project
from apps.utils.rest.renderers import BrowsableAPIRendererWithoutForms

from .serializers import (
    ShippingArchivedTripInfoSerializer, ShippingTripInfoSerializer, ShippingTripSetupSerializer, TripArchiveSerializer,
    TripOrgQualityReportSerializer, TripSummaryReportSerializer,
)
from .utils.renderer import OrgQualityCSVRenderer
from .utils.trip import schedule_trip_archive, set_device_to_active

logger = logging.getLogger(__name__)


def _get_device_and_check_permission(slug, user, permission):
    device = get_object_or_404(Device, slug=slug)
    org = device.org
    if not org or not org.has_permission(user, permission):
        raise drf_exceptions.PermissionDenied('Access Denied due to lack of sufficient permissions')

    return device


class APIShippingTripStatusReportViewSet(APIView):
    """
    Project Trip Status Report
    """
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self, slug):
        project = get_object_or_404(Project, slug=slug)
        org = project.org
        if not org or not org.has_permission(self.request.user, 'can_read_device_properties'):
            raise drf_exceptions.PermissionDenied('Access Denied due to lack of sufficient permissions')

        return project

    @swagger_auto_schema(
        operation_id='Project Trip Status Report',
        responses={
            200: TripSummaryReportSerializer(),
        }
    )
    def get(self, request, project_slug, format=None):
        """
        Analyze all devices in project, and report the state of all known trips.

        If a trip has been setup, report if there has been any updates.

        If a trip has ended, indicate so.

        Also report selected properties based on the `:report:trip_status:config` config attribute
        set on the given project. Defaults to `Ship From` and `Ship To`
        """

        project = self.get_object(project_slug)
        serializer = TripSummaryReportSerializer(project)

        return Response(serializer.data)


class APIShippingArchiveQualitySummaryReportViewSet(APIView):
    """
    Organization Quality Report
    """
    permission_classes = (permissions.IsAuthenticated,)
    renderer_classes = (JSONRenderer, BrowsableAPIRendererWithoutForms, OrgQualityCSVRenderer)

    def get_object(self, slug):
        org = get_object_or_404(Org, slug=slug)
        if not org or not org.has_permission(self.request.user, 'can_manage_org_and_projects'):
            raise drf_exceptions.PermissionDenied('Access Denied due to lack of sufficient permissions')

        return org

    @swagger_auto_schema(
        operation_id='Organization Quality Report',
        responses={
            200: TripOrgQualityReportSerializer(),
        }
    )
    def get(self, request, org_slug, format=None):
        """
        Report all organization archived trips, generating the following for each trip:

        * Archive information. e.g. label
        * Trip Properties
        * Trip Summary Report
        """

        org = self.get_object(org_slug)
        serializer = TripOrgQualityReportSerializer(org)

        return Response(serializer.data)


class APIShippingTripViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    API to get Shipping Trip Information
    The information includes:
    - Start Trip (after mask)
    - End Trip (after mask)
    - Status
    - List of variables and their APIs to get data

    """
    lookup_field = 'slug'
    permission_classes = (IsMemberOnly,)

    def get_serializer_class(self):
        slug = self.kwargs['slug']

        try:
            IOTileDeviceSlug(slug)
            return ShippingTripInfoSerializer
        except ValueError:
            return ShippingArchivedTripInfoSerializer

    def get_object(self, permission=None):
        """
        Get object based on given slug. prepend '0000' as needed to
        properly format the device gid='d--0000-0000-0000-0001'

        Returns: Device if it exist

        """
        slug = self.kwargs['slug']

        try:
            device_or_block_slug = IOTileDeviceSlug(slug)
            device_or_block = get_object_or_404(Device, slug=str(device_or_block_slug))
        except ValueError:
            device_or_block_slug = IOTileBlockSlug(slug)
            device_or_block = get_object_or_404(DataBlock, slug=str(device_or_block_slug))

        if permission:
            org = device_or_block.org
            if org.has_permission(user=self.request.user, permission=permission):
                return device_or_block
        elif device_or_block.has_access(self.request.user):
            return device_or_block

        raise drf_exceptions.PermissionDenied('Access Denied due to lack of sufficient permissions')

    @swagger_auto_schema(
        method='post',
        operation_id='Shipping Trip Setup',
        request_body=ShippingTripSetupSerializer,
        responses={
            status.HTTP_202_ACCEPTED: DeviceSerializer(),
        }
    )
    @action(methods=['post'], detail=True)
    def setup(self, request, slug=None):
        """
        Activate shipping device for the trip
        """
        serializer = ShippingTripSetupSerializer(data=request.data)
        if serializer.is_valid():
            device = self.get_object('can_modify_device')

            if device.busy:
                raise drf_exceptions.PermissionDenied('Device is busy. Operation cannot be completed at this time')

            if device.state != 'N0':
                raise drf_exceptions.ValidationError('Device must be in Inactive State before it can be setup for a trip')

            set_device_to_active(device, self.request.user)
            serializer = DeviceSerializer(device)
            return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        method='post',
        operation_id='Shipping Trip Archive',
        request_body=TripArchiveSerializer,
        responses={
            status.HTTP_201_CREATED: TripArchiveSerializer(),
        }
    )
    @action(methods=['post'], detail=True)
    def archive(self, request, slug=None):
        """
        Mark trip as completed, archive and return the device to the available list
        """
        device = self.get_object('can_manage_org_and_projects')

        org = device.org

        if device.busy:
            raise drf_exceptions.PermissionDenied('Device is busy. Operation cannot be completed at this time')

        if device.state != 'N1':
            raise drf_exceptions.ValidationError('Device must be in Active State before it can be archived')

        # Create DataBlock object using DataBlock serializer (scheduling on save())
        serializer = TripArchiveSerializer(data=request.data, context={'request': request, 'device': device})
        if serializer.is_valid():
            block = serializer.save(created_by=self.request.user, org=org, sg=device.sg)
            pid = schedule_trip_archive(device=device, block=block, user=self.request.user)
            serializer.set_pid(pid)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


