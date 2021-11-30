import json

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404

import django_filters
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.utils.api_key_utils import get_org_slug_from_apikey
from apps.utils.rest.permissions import HasAuthAPIKeyNoOrg, IsStaffOrReadOnly, ReadOnly

from .models import *
from .serializers import DeviceSlotReadOnlySerializer, DeviceSlotSerializer, DeviceTemplateSerializer


class APIDeviceTemplateViewSet(viewsets.ModelViewSet):
    """
    Not Documented. For Internal Use Only.
    """
    lookup_field = 'slug'
    queryset = DeviceTemplate.objects.none()
    serializer_class = DeviceTemplateSerializer
    permission_classes = [HasAuthAPIKeyNoOrg&ReadOnly | IsStaffOrReadOnly]
    filterset_fields = ('created_by', 'org__slug',)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        if self.request.user.is_staff and self.request.GET.get('staff', ''):
            qs = DeviceTemplate.objects.all()
        else:
            qs = DeviceTemplate.objects.filter(active=True)
        return qs.select_related('org').prefetch_related('slots', 'slots__component')

    def perform_create(self, serializer):
        # Include the owner attribute directly, rather than from request data.
        instance = serializer.save(created_by=self.request.user)

    @action(methods=['get', 'post'], detail=True)
    def slot(self, request, slug=None):
        """
        POST: Create a new DeviceSlot.
        Payload :
        - number: (required) int with slot number
        - component: (required) str of component slug
        """
        obj = get_object_or_404(DeviceTemplate, slug=slug)
        if request.method == 'GET':
            templates = obj.slots.all().order_by('number')
            page = self.paginate_queryset(templates)
            if page is not None:
                serializer = DeviceSlotReadOnlySerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = DeviceSlotSerializer(templates, many=True)
            return Response(serializer.data)
        elif request.method == 'POST':
            if self.request.user.is_admin:
                try:
                    # There should only be one entry for a DT per slot number
                    slot = DeviceSlot.objects.get(template=obj.id, number=request.data['number'])
                    serializer = DeviceSlotSerializer(slot, data=request.data, partial=False)
                    if serializer.is_valid():
                        serializer.save()
                        return Response(serializer.data)
                except DeviceSlot.DoesNotExist:
                    # Create a new slot
                    serializer = DeviceSlotSerializer(data=request.data)
                    if serializer.is_valid():
                        serializer.save(template=obj)
                        return Response(serializer.data, status=status.HTTP_201_CREATED)

                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response('Illegal Method', status=status.HTTP_400_BAD_REQUEST)
