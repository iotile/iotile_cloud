import json

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404

import django_filters
from rest_framework import mixins, status, viewsets

from apps.utils.rest.permissions import IsStaffOrReadOnly

from .models import *
from .serializers import ComponentSerializer


class APIComponentViewSet(viewsets.ModelViewSet):
    """
    Not Documented. For Internal Use Only.
    """
    lookup_field = 'slug'
    queryset = Component.objects.none()
    serializer_class = ComponentSerializer
    permission_classes = (IsStaffOrReadOnly,)
    filterset_fields = ('created_by',)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)

    def get_queryset(self):
        return Component.objects.all()

    def perform_create(self, serializer):
        # Include the owner attribute directly, rather than from request data.
        instance = serializer.save(created_by=self.request.user)
