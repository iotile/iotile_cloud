import json
from django.http import HttpResponse, Http404
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.db import IntegrityError

import django_filters
from rest_framework import viewsets
from rest_framework import mixins
from rest_framework import status
from rest_framework import filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from apps.project.serializers import ProjectSerializer
from apps.utils.rest.pagination import LargeResultsSetPagination

from apps.org.permissions import IsMemberOnly
from .models import *
from .serializers import *


class FleetApiFilter(django_filters.rest_framework.FilterSet):
    org = django_filters.CharFilter(method='filter_by_org', label='Org')
    device = django_filters.CharFilter(method='filter_by_device', label='Device')
    class Meta:
        model = Fleet
        fields = ['org', 'device', 'is_network']

    def filter_by_org(self, queryset, name, value):
        org = get_object_or_404(Org, slug=value)
        return queryset.filter(org=org)

    def filter_by_device(self, queryset, name, value):
        device = get_object_or_404(Device, slug=value)
        # Get Fleet member objects for this device
        return queryset.filter(id__in=[f.id for f in device.fleet_set.all()])


class APIFleetViewSet(viewsets.ModelViewSet):
    """
    A Fleet represents a group of devices that are part of a Network and/or share the same configuration
    
    If fleet represents a network, at least one device should behave as a Gateway, able to scan all other devices
    """
    lookup_field = 'slug'
    queryset = Fleet.objects.none()
    serializer_class = FleetSerializer
    permission_classes = (IsMemberOnly,)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = FleetApiFilter

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        if self.request.user.is_staff and self.request.GET.get('staff', ''):
            return Fleet.objects.all().prefetch_related('created_by', 'org')

        return Fleet.objects.user_fleets_qs(self.request.user).prefetch_related('created_by', 'org')

    def perform_create(self, serializer):
        """
        Create a new Fleet
        """
        org = serializer.validated_data['org']
        if not org.has_permission(self.request.user, 'can_manage_ota'):
            raise PermissionDenied('User has no permissions to manage devices')

        serializer.save(created_by=self.request.user)

    @action(methods=['get'], detail=True)
    def devices(self, request, slug=None):
        """
         Return list of devices which are part of the fleet
        """
        fleet = self.get_object()

        qs = FleetMembership.objects.filter(fleet=fleet)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = FleetMembershipSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = FleetMembershipSerializer(qs, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(methods=['post'], detail=True)
    def register(self, request, slug=None):
        """
         Add a device with the fleet. Device and Fleet must be part of same Org
        """
        fleet = self.get_object()

        if not fleet.org.has_permission(self.request.user, 'can_manage_ota'):
            raise PermissionDenied('User has no permissions to manage devices')

        serializer = FleetMembershipSerializer(data=request.data)
        if serializer.is_valid():
            device = serializer.validated_data['device']
            if (request.user.is_staff or (fleet.has_access(self.request.user) and device.has_access(self.request.user))):
                if not FleetMembership.objects.filter(device=device, fleet=fleet).exists():
                    instance = serializer.save(fleet=fleet)
                else:
                    return Response({'error': 'Device {} already exists in fleet'.format(device.slug)}, status=status.HTTP_400_BAD_REQUEST)

                return Response(serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': 'User has no access to Device'}, status=status.HTTP_403_FORBIDDEN)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['post'], detail=True)
    def deregister(self, request, slug=None):
        """
         Remove a device from the fleet
        """
        fleet = self.get_object()

        if not fleet.org.has_permission(self.request.user, 'can_manage_ota'):
            raise PermissionDenied('User has no permissions to manage devices')

        serializer = FleetMembershipSerializer(data=request.data)
        if serializer.is_valid():
            device = serializer.validated_data['device']
            if (request.user.is_staff or (fleet.has_access(self.request.user) and device.has_access(self.request.user))):
                try:
                    membership = FleetMembership.objects.get(device=device, fleet=fleet)
                except FleetMembership.DoesNotExist:
                    return Response({'error': 'Device not found'}, status=status.HTTP_400_BAD_REQUEST)

                membership.delete()
                return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
            else:
                return Response({'error': 'User has no access to Device'}, status=status.HTTP_403_FORBIDDEN)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
