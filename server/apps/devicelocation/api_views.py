import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone

import django_filters
from rest_framework import viewsets
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import filters
from rest_framework import exceptions as drf_exceptions

from drf_yasg import openapi
from drf_yasg.utils import no_body, swagger_auto_schema

from apps.utils.rest.pagination import LargeResultsSetPagination
from apps.utils.timezone_utils import str_to_dt_utc
from apps.utils.data_mask.mask_utils import get_data_mask_date_range_for_slug
from apps.utils.iotile.variable import SYSTEM_VID

from .serializers import *
from .models import *
from .filters import DeviceLocationFilter

user_model = get_user_model()

# Get an instance of a logger
logger = logging.getLogger(__name__)


class APIDeviceLocationViewSet(viewsets.ModelViewSet):
    """
    Get all locations for a given device.
    
    * StreamNote is a time based note

    This API requires a filter argument, in the form of:
    
    * `/api/v1/location/?target=d--0000-0000-0000-aaaa`  to show all locations for a given device

    * Use `&mask=1` if you want the start/end timestamp to respect any device data mask that may be set

    """
    queryset = DeviceLocation.objects.all().select_related('user')
    serializer_class = DeviceLocationSerializer
    permission_classes = (IsAuthenticated,)
    pagination_class = LargeResultsSetPagination
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = DeviceLocationFilter

    def _update_device(self, location):
        """
        Update current device location, usually with last known DeviceLocation
        :param location: location to update from
        """
        device = location.target
        device.lat = location.lat
        device.lon = location.lon
        device.save()

    def _check_target_access(self, target_slug):
        """
        Ensure user has access to read locations for target
        """

        n, target = get_object_by_slug(target_slug)
        if not target or not target.has_access(self.request.user):
            raise drf_exceptions.PermissionDenied

        return n, target

    def get_queryset(self):
        """
        This view should return a list of all records based on the target and if mask=1
        """
        qs = DeviceLocation.objects.none()
        use_mask = self.request.GET.get('mask', '') == '1'
        filter_value = self.request.GET.get('target', None)
        if filter_value:
            obj_type, obj = get_object_by_slug(filter_value)
            if obj and obj.org:
                if obj.org.has_permission(self.request.user, 'can_read_device_locations'):
                    qs = DeviceLocation.objects.filter(target_slug=filter_value)

                    if use_mask and obj and obj.slug[0] in ['d', 'b', 's']:
                        mask_stream_slug = obj.get_stream_slug_for(SYSTEM_VID['DEVICE_DATA_MASK'])
                        mask = get_data_mask_date_range_for_slug(mask_stream_slug)
                        if mask and mask['start']:
                            mask_start = str_to_dt_utc(mask['start'])
                            qs = qs.filter(timestamp__gte=mask_start)
                        if mask and mask['end']:
                            mask_end = str_to_dt_utc(mask['end'])
                            qs = qs.filter(timestamp__lt=mask_end)

        return qs

    def get_object(self):
        try:
            id = int(self.kwargs['pk'])
        except Exception as e:
            raise drf_exceptions.ValidationError('Location ID must be a integer')

        location = get_object_or_404(DeviceLocation, pk=id)

        if self.request.user.is_staff:
            return location

        target = location.target
        if target.org.has_permission(self.request.user, 'can_read_device_locations'):
            return location

        raise PermissionDenied

    def perform_create(self, serializer):
        entries = []
        many = isinstance(serializer.validated_data, list)

        if many:
            count = 0
            # 1. Check that all entries are for same target
            target_set = set()
            for item in serializer.validated_data:
                target_slug = item['target_slug']
                target_set.add(target_slug)
            if len(target_set) != 1:
                raise drf_exceptions.ValidationError(
                    'Found more than one target. All entries must be for same target.'
                )
            target_slug = target_set.pop()
            n, target = self._check_target_access(target_slug)

            for item in serializer.validated_data:
                location = DeviceLocation(user=self.request.user, **item)
                entries.append(location)
                count += 1

            logger.info('Committing batch of {0} data note entries'.format(count))
            if count:
                DeviceLocation.objects.bulk_create(entries)
                # Also Update Device with last entry
                if n == 'device':
                    self._update_device(entries[-1])
                last = DeviceLocationSerializer(entries[-1])
                return {
                    'count': count,
                    'last': last.data
                }
        else:
            target_slug = serializer.validated_data['target_slug']
            n, target = self._check_target_access(target_slug)

            location = serializer.save(user=self.request.user)
            if n == 'device':
                self._update_device(location)

            return serializer.data

    @swagger_auto_schema(
        responses={
            201: DeviceLocationSerializer(many=False),
            400: 'More than one target found in payload',
            403: 'Access to target object denied',
            404: 'Device Location or Target not found'
        }
    )
    def create(self, request, *args, **kwargs):
        """
        Add a new device GPS coordinate with a timestamp.

        Either a single location can be added, or a list of locations.
        If list, simply add the list of payloads inside a [] list.
        In this case, the response will include

            {
                count: <num>,
                last: <last location recorded>
            }
        """
        many = isinstance(request.data, list)
        serializer = self.get_serializer(data=request.data, many=many)
        serializer.is_valid(raise_exception=True)
        data = self.perform_create(serializer)
        return Response(data, status=status.HTTP_201_CREATED)
