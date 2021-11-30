import json
import logging
import pprint

from django.db.utils import IntegrityError
from django.utils import timezone

from drf_yasg import openapi
from drf_yasg.utils import no_body, swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.physicaldevice.models import Device
from apps.streamnote.models import StreamNote
from apps.utils.rest.exceptions import ApiIllegalFilterOrTargetException, ApiIllegalPkException
from apps.utils.rest.permissions import IsStaffOrReadOnly

from .filters import *
from .models import *
from .serializers import *

logger = logging.getLogger(__name__)


class APIConfigAttributeNameViewSet(viewsets.ModelViewSet):
    """
    Available system wide configuration attribute names to be set of a given object (target)

    list: Get list of available Configuration Attribute Names

    create: [Staff Only] Create mew Configuration Attribute Names

    """
    queryset = ConfigAttributeName.objects.all()
    serializer_class = ConfigAttributeNameSerializer
    permission_classes = (IsStaffOrReadOnly,)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = ConfigAttributeNameFilter

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @swagger_auto_schema(manual_parameters=[
        openapi.Parameter(
            name='search', in_=openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            description="Search term (to match attribute name)"
        ),
        openapi.Parameter(
            name='tag', in_=openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            description="List records with given tag"
        ),
    ])
    def list(self, request, *args, **kwargs):
        return super(APIConfigAttributeNameViewSet, self).list(request, args)


class APIConfigAttributeViewSet(viewsets.ModelViewSet):
    """
    API to get or set configuration attributes on a given object (target)

    """
    queryset = ConfigAttribute.objects.all()
    serializer_class = ConfigAttributeSerializer
    permission_classes = (IsAuthenticated,)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = ConfigAttributeFilter

    def _log_note(self, config_attr):
        note = 'Attribute {} was changed to:'.format(config_attr.name)
        if isinstance(config_attr.data, dict):
            for key in config_attr.data.keys():
                note += '\n--> {}: {}'.format(key, config_attr.data[key])
        else:
            note += '--> {}'.format(config_attr.data)
        StreamNote.objects.create(
            target_slug=config_attr.target,
            timestamp=timezone.now(),
            note=note,
            type='si',
            created_by=self.request.user)

    def get_object(self):
        try:
            pk = int(self.kwargs['pk'])
        except Exception:
            raise ApiIllegalPkException

        obj = get_object_or_404(ConfigAttribute, pk=pk)
        target_slug = obj.target
        _, target = get_object_by_slug(target_slug)
        if not target or not target.has_access(self.request.user):
            raise drf_exceptions.PermissionDenied
        return obj

    def perform_create(self, serializer):
        target_slug = serializer.validated_data['target']
        target_slug = target_slug.lower()
        target_type, target = get_object_by_slug(target_slug)
        if not target or not target.has_access(self.request.user):
            raise drf_exceptions.PermissionDenied

        try:
            config_attr = serializer.save(updated_by=self.request.user, target=target)
        except ValidationError:
            raise ApiIllegalFilterOrTargetException(f'Illegal target {target}')

        if 'log_as_note' in serializer.validated_data and serializer.validated_data['log_as_note']:
            if target_type == 'device':
                self._log_note(config_attr)

    def update(self, request, *args, **kwargs):
        return Response(
            data={'error': 'PUT and PATCH methods are not supported; use POST with the right target'},
            status=400
        )

    @swagger_auto_schema(
        operation_id='config_attr_create',
        responses={
            201: ConfigAttributeSerializer(many=False),
            400: 'Configuration attribute name not found',
            403: 'Access to target object denied',
        }
    )
    def create(self, request, *args, **kwargs):
        """
        Create a new Configuration Attribute with the given name and assigned to the given target.

        Name must match an existing Configuration Attribute Name record.

        If attribute with same name already exist for given target, overwrite with new data.
        """
        return super(APIConfigAttributeViewSet, self).create(request, args)

    @swagger_auto_schema(
        operation_id='config_attr_list',
        manual_parameters=[
            openapi.Parameter(
                name='target', in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Target Slug. e.g. ^org-name, @username, d--0000-0000-0000-0001",
                required=True
            ),
            openapi.Parameter(
                name='name_q', in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Search term (to match attribute name)"
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        """
        List all configuration attributes for the given required target.

        Use the search field to find attributes that contain the given string
        """
        return super(APIConfigAttributeViewSet, self).list(request, args)

    def destroy(self, request, *args, **kwargs):
        """
        Delete Configuration Attribute with given id
        """
        obj = self.get_object()
        return super(APIConfigAttributeViewSet, self).destroy(request, args, kwargs)

    @swagger_auto_schema(
        method='get',
        manual_parameters=[
            openapi.Parameter(
                name='target', in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Target Slug. e.g. ^org-name, @username, d--0000-0000-0000-0001",
                required=True
            ),
            openapi.Parameter(
                name='name', in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Configuration attribute name to search for",
                required=True
            ),
            openapi.Parameter(
                name='name_q', in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="N/A",
                required=False
            ),
            openapi.Parameter(
                name='page', in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="N/A"
            ),
            openapi.Parameter(
                name='page_size', in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="N/A"
            ),
        ],
        responses={
            200: ConfigAttributeSerializer(many=False),
            400: 'Bad Request',
            403: 'Access to target object denied',
            404: 'No configuration attribute found'
        }
    )
    @action(methods=['get'], detail=False)
    def search(self, request):
        """
        Search given target for a configuration attribute. If not found, search higher level objects
        until found.

        Search Path:

        - Device
        - Project
        - Org
        - User
        """
        target_slug = self.request.GET.get('target', None)
        name = self.request.GET.get('name', None)
        if target_slug and name:
            # target_slug = target_slug.lower()
            _, target = get_object_by_slug(target_slug)
            if target:
                if target.has_access(self.request.user):
                    obj = ConfigAttribute.objects.get_attribute_by_priority(
                        target_slug=target_slug,
                        name=name,
                        user=self.request.user
                    )
                    if obj:
                        serializer = ConfigAttributeSerializer(obj)
                        return Response(serializer.data)
                    else:
                        raise drf_exceptions.NotFound
                else:
                    raise drf_exceptions.PermissionDenied

        return Response({'error': 'Missing target and/or name'}, status=status.HTTP_400_BAD_REQUEST)
