
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

import django_filters
from rest_framework import viewsets

from apps.utils.rest.permissions import IsStaffOrReadOnly

from .models import *
from .serializers import OrgTemplateSerializer


class APIOrgTemplateViewSet(viewsets.ModelViewSet):
    """
    Organization Templates defines the Organization View Skin
    to be used for a given Organization.
    Only Vendors can create these records
    """
    lookup_field = 'slug'
    queryset = OrgTemplate.objects.none()
    serializer_class = OrgTemplateSerializer
    permission_classes = (IsStaffOrReadOnly, )
    filterset_fields = ('created_by', )
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        if self.request.user.is_staff and self.request.GET.get('staff', ''):
            return OrgTemplate.objects.all()

        return OrgTemplate.objects.filter(active=True)

    def perform_create(self, serializer):
        # Include the owner attribute directly, rather than from request data.
        instance = serializer.save(created_by=self.request.user)
