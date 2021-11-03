from rest_framework import viewsets
from rest_framework import mixins
from rest_framework.permissions import IsAdminUser

from .models import *
from .serializers import *


class APICreateDeviceKeyViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """
    API to upload Device Authentication Keys

    Access Restricted.
    """
    queryset = DeviceKey.objects.none()
    serializer_class = DeviceKeyCreateSerializer
    permission_classes = (IsAdminUser, )

    def perform_create(self, serializer):
        # Include the owner attribute directly, rather than from request data.
        instance = serializer.save(created_by=self.request.user)
