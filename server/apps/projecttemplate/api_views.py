
import django_filters
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied

from rest_framework import viewsets

from apps.utils.rest.permissions import IsStaffOrReadOnly
from .models import *
from .serializers import ProjectTemplateSerializer


class APIProjectTemplateViewSet(viewsets.ModelViewSet):
    """
    Not Documented. For Internal Use Only.
    """
    lookup_field = 'slug'
    queryset = ProjectTemplate.objects.none()
    serializer_class = ProjectTemplateSerializer
    permission_classes = (IsStaffOrReadOnly, )
    filterset_fields = ('created_by', 'org__slug',)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        if self.request.user.is_staff and self.request.GET.get('staff', ''):
            return ProjectTemplate.objects.all()

        return ProjectTemplate.objects.filter(active=True)

    def perform_create(self, serializer):
        # Include the owner attribute directly, rather than from request data.
        instance = serializer.save(created_by=self.request.user)
