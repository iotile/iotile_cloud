import logging

from django.utils.decorators import method_decorator

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets

from apps.utils.rest.cached_views import cache_on_auth
from apps.utils.rest.permissions import HasAuthAPIKeyNoOrg, IsStaffOrReadOnly, ReadOnly

from .models import VarType
from .serializers import VarTypeReadOnlySerializer

logger = logging.getLogger(__name__)


class APIVarTypeViewSet(viewsets.ModelViewSet):
    """
    A VarType represents a Variable Type.
    Like with a typed SW program, the Variable needs to have a type, so the cloud know how to process it
    or display it.
    For example, a water meter sensor will have a VarType representing Volume,
    with liters as its database stored representation, but with input and output units representing Gallons, Liters
    and other units of volume
    """
    lookup_field = 'slug'
    queryset = VarType.objects.none()
    serializer_class = VarTypeReadOnlySerializer
    permission_classes = [HasAuthAPIKeyNoOrg&ReadOnly | IsStaffOrReadOnly]
    filterset_fields = ('created_by',)
    filter_backends = (filters.SearchFilter, DjangoFilterBackend,)
    search_fields = ('name',)

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        return VarType.objects.all().prefetch_related('input_units', 'output_units', 'decoder')

    def perform_create(self, serializer):
        # Include the owner attribute directly, rather than from request data.
        instance = serializer.save(created_by=self.request.user)

    @method_decorator(cache_on_auth(60 * 15, key_prefix="api:vartype"))
    def dispatch(self, *args, **kwargs):
        return super(APIVarTypeViewSet, self).dispatch(*args, **kwargs)
