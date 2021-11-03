# Modules needed to execute back-end jobs requested by server
import logging
import csv
import pytz
from datetime import datetime, timedelta
from django.utils.timezone import localtime
from django.db.models import Q

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

import django_filters
from django_filters.rest_framework import FilterSet, DjangoFilterBackend

from apps.utils.rest.custom_serializers import MultiSerializerViewSetMixin
from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework import mixins, generics
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from rest_framework import filters

from iotile_cloud.utils.gid import IOTileProjectSlug

from apps.utils.gid.convert import formatted_gvid, formatted_gsid, get_device_and_block_by_did
from apps.utils.rest.pagination import SuperLargeResultsSetPagination, LargeResultsSetPagination
from apps.utils.uuid_utils import validate_uuid
from apps.project.models import Project
from apps.streamdata.serializers import StreamIdDataSerializer
from apps.streamevent.serializers import StreamIdEventDataSerializer
from apps.streamdata.utils import get_stream_output_mdo
from apps.vartype.serializers import VarTypeReadOnlySerializer

from .serializers import *
from .models import *
from .helpers import StreamDataQueryHelper, StreamDataDisplayHelper

user_model = get_user_model()

# Get an instance of a logger
logger = logging.getLogger(__name__)


class StreamVariableFilter(FilterSet):
    project = django_filters.CharFilter(method='filter_by_project')
    org = django_filters.CharFilter(method='filter_by_org')
    class Meta:
        model = StreamVariable
        fields = ['project']

    def _validate_uuid(self, uuid_string):
        return validate_uuid(uuid_string)

    def filter_by_org(self, queryset, name, value):
        org = get_object_or_404(Org, slug=value)
        return queryset.filter(org=org)

    def filter_by_project(self, queryset, name, value):
        if not self._validate_uuid(value):
            try:
                project_slug = IOTileProjectSlug(value)
                return queryset.filter(project__slug=str(project_slug))
            except ValueError:
                return queryset.none()

        return queryset.filter(Q(project_id=value) | Q(project__isnull=True))


class APIStreamVariableViewSet(viewsets.ModelViewSet):
    """
    Get all Stream Variable data.
    Stream Variables are the variables that a data stream on a Device is tracking. `Stream`
    is used to associate the Project-level Stream Variable to an individual Device.

    Variables are either Project variables (custom variables defined by the SensorGraph)
    or Manufacturer Variables (defined by the Device template).

    """
    lookup_field = 'slug'
    queryset = StreamVariable.objects.none()
    serializer_class = StreamVariableSerializer
    permission_classes = (IsAuthenticated,)
    pagination_class = LargeResultsSetPagination
    filterset_class = StreamVariableFilter
    filter_backends = (filters.SearchFilter, DjangoFilterBackend,)
    search_fields = ('name',)

    def get_queryset(self):
        """
        Variables the user has access to.
        """
        if self.request.user.is_staff and (self.request.GET.get('staff', '0') == '1'):
            qs = StreamVariable.objects.all().select_related(
                'input_unit', 'output_unit', 'var_type', 'org', 'project'
            )
        else:
            qs = StreamVariable.objects.user_variables_qs(self.request.user).select_related(
                'input_unit', 'output_unit', 'var_type', 'org', 'project'
            )

            # If requested, also include template variables
            if self.request.GET.get('include_templates', ''):
                project_id = self.request.GET.get('project', None)
                if project_id:
                    '''
                    project = get_object_or_404(Project, pk=project_id)
                    template = project.project_template
                    '''
                    # For now, just return all system variables
                    template_qs = StreamVariable.objects.system_variables_qs()
                    qs = qs | template_qs

        return qs

    def get_object(self):
        """
        Get object based on given slug. prepend '0000' as needed to
        properly format the device gid='d--0000-0000-0000-0001'

        Returns: Device if it exist

        """
        slug = self.kwargs['slug']
        slug_elements = slug.split('--')
        if len(slug_elements) == 3:
            slug = formatted_gvid(pid=slug_elements[1], vid=slug_elements[2])

        var = get_object_or_404(StreamVariable, slug=slug)

        if var.has_access(self.request.user):
            return var

        raise PermissionDenied

    def perform_create(self, serializer):
        # Include the owner attribute directly, rather than from request data.
        project = serializer.validated_data['project']

        variable = serializer.save(created_by=self.request.user, org=project.org)

        # Create Stream IDs as needed based on this new variable
        # StreamId.objects.create_after_new_variable(var=variable)

    def perform_update(self, serializer):
        variable = serializer.save()

    @action(methods=['get'], detail=True)
    def type(self, request, slug=None):
        """
        Get the Type for a single Stream Variable.
        """
        variable = self.get_object()
        var_type = variable.var_type
        serializer = VarTypeReadOnlySerializer(var_type)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        """
        Creates a Variable object.
        Variable.names represent the Device port name and should always be unique
        for the type of Device (ie: POD1 always has 'IO1' and 'IO2').
        """
        return super(APIStreamVariableViewSet, self).create(request)

    def retrieve(self, request, *args, **kwargs):
        """Returns a single Variable item"""
        return super(APIStreamVariableViewSet, self).retrieve(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """Updates a single Variable item"""
        return super(APIStreamVariableViewSet, self).update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Partially update a Variable """
        return super(APIStreamVariableViewSet, self).partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Staff Only.
        Delete a Variable.
        """
        if not request.user.is_staff:
            return Response({'error': 'Restricted Access. Contact Arch'}, status=status.HTTP_400_BAD_REQUEST)
        return super(APIStreamVariableViewSet, self).destroy(request, *args, **kwargs)


# filterset_fields = ('created_by', 'project', 'org__slug', 'device__slug', 'variable')
class StreamIdFilter(FilterSet):
    project = django_filters.CharFilter(method='filter_by_project')
    org__slug = django_filters.CharFilter(method='filter_by_org')
    org = django_filters.CharFilter(method='filter_by_org')
    device__slug = django_filters.CharFilter(method='filter_by_device')
    device = django_filters.CharFilter(method='filter_by_device')
    block = django_filters.CharFilter(method='filter_by_block')
    variable = django_filters.CharFilter(method='filter_by_variable')
    class Meta:
        model = StreamId
        fields = ['project', 'org', 'org__slug', 'device', 'device__slug', 'variable', 'block', 'enabled',]

    def filter_by_project(self, queryset, name, value):
        # Filter by project using either UUID or Slug
        if not validate_uuid(value):
            try:
                project_slug = IOTileProjectSlug(value)
                return queryset.filter(project__slug=str(project_slug), block__isnull=True)
            except Exception:
                return queryset.none()

        return queryset.filter(project_id=value, block__isnull=True)

    def filter_by_org(self, queryset, name, value):
        org = get_object_or_404(Org, slug=value)
        return queryset.filter(org=org, block__isnull=True)

    def filter_by_device(self, queryset, name, value):
        parts = value.split('--')
        if parts[0] == 'd':
            block_id, device_id = get_device_and_block_by_did(value)
            if device_id:
                if block_id > 0:
                    return queryset.filter(device_id=device_id, block_id=block_id)
                else:
                    return queryset.filter(device_id=device_id, block__isnull=True)
            return queryset.none()
        elif parts[0] == 'b':
            block = get_object_or_404(DataBlock, slug=value)
            return queryset.filter(block=block)
        else:
            raise PermissionDenied('Illegal Device ID')

    def filter_by_block(self, queryset, name, value):
        block = get_object_or_404(DataBlock, slug=value)
        return queryset.filter(block=block)

    def filter_by_variable(self, queryset, name, value):
        variable = get_object_or_404(StreamVariable, slug=value)
        return queryset.filter(variable=variable, block__isnull=True)


class APIStreamIdViewSet(MultiSerializerViewSetMixin, viewsets.ModelViewSet):
    """
    Get all Stream information
    
    A Stream represents the connection between a Device and the Variables that
    the Device is tracking. 
    
    `Data` will be associated with a particular Stream object.
    """
    lookup_field = 'slug'
    queryset = StreamId.objects.none()
    serializer_class = StreamIdSerializer
    serializer_action_classes = {
        'create': StreamIdCreateSerializer,
        'update': StreamIdSerializer,
        'partial_update': StreamIdSerializer,
        'list': StreamIdSerializer,
        'retrieve': StreamIdSerializer,
    }
    permission_classes = (IsAuthenticated,)
    # TODO: Change back to LargeResultsSetPagination
    pagination_class = SuperLargeResultsSetPagination
    filterset_class = StreamIdFilter
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        if self.request.user.is_staff and (self.request.GET.get('staff', '0') == '1'):
            qs = StreamId.objects.all()
        else:
            qs = StreamId.objects.user_streams_qs(self.request.user)

        if self.request.GET.get('virtual', '0') == '1':
            # For virtual streams, both device and block should be Null
            qs = qs.filter(Q(block_id__isnull=True, device__isnull=True))

        elif not self.request.GET.get('device', None):
            # If explicitly giving a device, then use even if device inactive or archived
            # IMPORTANT for WebApp as that is how it queries to get streams for an archive (i.e. using ?device=)

            if self.request.GET.get('archived', '0') == '1' or self.request.GET.get('block', None):
                # If archived=1, include streams from archived devices
                qs = qs.filter(Q(block_id__isnull=False))
            elif self.request.GET.get('all', '0') != '1':
                # If all=1, include streams from inactive or archived devices
                qs = qs.filter(Q(device__active=True) & Q(block_id__isnull=True))

        return qs.select_related(
            'device', 'block', 'org', 'project', 'var_type', 'input_unit', 'output_unit'
        )

    def get_object(self):
        """
        Get object based on given slug. prepend '0000' as needed to
        properly format the device gid='s--0000-0001--0000-0000-0000-0001--0001'

        Returns: Stream if it exist

        """
        slug = self.kwargs['slug']
        slug_elements = slug.split('--')
        if len(slug_elements) == 4:
            slug = formatted_gsid(pid=slug_elements[1], did=slug_elements[2], vid=slug_elements[3])

        stream = get_object_or_404(StreamId, slug=slug)

        if stream.org.has_permission(self.request.user, 'can_read_stream_data'):
            return stream

        raise PermissionDenied

    def perform_create(self, serializer):
        variable = serializer.validated_data['variable']
        device = serializer.validated_data.get('device', None)
        if not variable.has_access(self.request.user):
            raise PermissionDenied
        if device and not device.has_access(self.request.user):
            raise PermissionDenied

        if device and (device.project != variable.project):
            raise NotFound('Project and Variable belong to different projects')

        stream = serializer.save(
            org=variable.org,
            project=variable.project,
            variable=variable,
            device=device,
            var_lid=variable.lid,
            var_name=variable.name,
            var_type=variable.var_type,
            input_unit=variable.input_unit,
            output_unit=variable.output_unit,
            data_type=variable.var_type.stream_data_type if variable.var_type is not None else '00',
            multiplication_factor=variable.multiplication_factor,
            division_factor=variable.division_factor,
            offset=variable.offset,
            mdo_type='S',
            raw_value_format=variable.raw_value_format,
            created_by=self.request.user
        )

    @swagger_auto_schema(
        method='get',
        responses={
            200: StreamIdDataSerializer(many=True),
            400: 'Bad Request'
        },
        manual_parameters=[
            openapi.Parameter(
                name='lastn', in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                description="Show last n data values"
            ),
            openapi.Parameter(
                name='start', in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Show data points with timestamp after this value"
            ),
            openapi.Parameter(
                name='end', in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Show data points with timestamp before this value"
            )
        ]
    )
    @action(methods=['get'], detail=True)
    def data(self, request, slug=None):
        """
        Get data for a given Stream
        """

        stream = self.get_object()
        helper = StreamDataQueryHelper(stream=stream)
        try:
            data = helper.get_data_for_filter(request.GET)
        except ValidationError as e:
            return Response({'error': 'Validation Error: {}'.format(e)}, status=status.HTTP_400_BAD_REQUEST)

        page = self.paginate_queryset(data)
        if page is not None:
            serializer = StreamIdDataSerializer(page, many=True, stream=stream)
            return self.get_paginated_response(serializer.data)

        serializer = StreamIdDataSerializer(data, many=True, stream=stream)
        return Response(serializer.data)

    @swagger_auto_schema(
        method='get',
        responses={
            200: 'Data in CSV form',
            400: 'Bad Request'
        },
        manual_parameters=[
            openapi.Parameter(
                name='lastn', in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                description="Show last n data values"
            ),
            openapi.Parameter(
                name='start', in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Show data points with timestamp after this value"
            ),
            openapi.Parameter(
                name='end', in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Show data points with timestamp before this value"
            )
        ]
    )
    @action(methods=['get'], detail=True)
    def csv(self, request, slug=None):
        """
        Get Stream data in CSV format
        """

        stream = self.get_object()
        helper = StreamDataQueryHelper(stream=stream)
        data = helper.get_data_for_filter(request.GET)

        response = HttpResponse()
        response['Content-Disposition'] = 'attachment; filename="{0}.csv"'.format(stream.slug)
        csv_writer = csv.DictWriter(response, ['Timestamp', 'Value'])
        csv_writer.writeheader()
        helper = StreamDataDisplayHelper(stream=stream)
        for item in data:
            try:
                timestamp = localtime(item.timestamp).strftime('%Y/%m/%d %H:%M:%S')
            except ValueError:
                aware = pytz.utc.localize(item.timestamp)
                timestamp = aware.strftime('%Y/%m/%d %H:%M:%S')
            csv_writer.writerow({
                'Timestamp': timestamp,
                'Value': helper.output_value(value=item.int_value)
            })
        return response

    @swagger_auto_schema(
        auto_schema = None
    )
    @action(methods=['get'], detail=True)
    def datatable(self, request, slug=None):
        """
        Get Stream data as a datatable
        """
        start = 1
        length = 1
        cols = [
            'timestamp',
            'int_value'
        ]

        if 'length' in request.GET:
            length = int(request.GET['length'])

        if 'start' in request.GET:
            start = int(request.GET['start'])

        stream = self.get_object()
        helper = StreamDataQueryHelper(stream=stream)
        data = helper.get_data_for_filter({})

        ordered_by_field = 0
        if 'order[0][column]' in request.GET:
            ordered_by_field = int(request.GET['order[0][column]'])

        logger.info('Sorted by {}'.format(ordered_by_field))
        order_by_str = cols[ordered_by_field]
        if 'order[0][dir]' in request.GET:
            sort_dir = request.GET['order[0][dir]']
            logger.info('Sort Dir {}'.format(sort_dir))
            if sort_dir == 'desc':
                order_by_str = '-{0}'.format(cols[ordered_by_field])

        logger.info('data will be sorted with order_by_str={0}'.format(order_by_str))
        data = data.order_by(order_by_str)

        if length == -1:
            logger.info('length={0}, start={1}, Show ALL'.format(length, start))
            serializer = StreamIdDataSerializer(data, many=True, stream=stream)
        else:
            page_num = int(start / length) + 1
            logger.info('length={0}, start={1}, page_num={2}'.format(length, start, page_num))
            p = Paginator(data, length)
            page = p.page(page_num)
            serializer = StreamIdDataSerializer(page.object_list, many=True, stream=stream)

        result = {}
        if 'sEcho' in request.GET:
            result['sEcho'] = request.GET['sEcho']

        if 'draw' in request.GET:
            result["draw"] = request.GET['draw']
        result["recordsTotal"] = data.count()
        result["recordsFiltered"] = data.count()
        result["data"] = serializer.data

        return Response(result)

    @swagger_auto_schema(
        auto_schema = None
    )
    @action(methods=['get'], detail=True)
    def eventtable(self, request, slug=None):
        """
        Get Stream event data as a datatable
        """
        start = 1
        length = 1
        cols = [
            'timestamp',
            'extra_data'
        ]

        if 'length' in request.GET:
            length = int(request.GET['length'])

        if 'start' in request.GET:
            start = int(request.GET['start'])

        stream = self.get_object()
        helper = StreamDataQueryHelper(stream=stream)
        events = helper.get_data_for_filter({}, event=True)

        ordered_by_field = 0
        if 'order[0][column]' in request.GET:
            ordered_by_field = int(request.GET['order[0][column]'])

        logger.info('Sorted by {}'.format(ordered_by_field))
        order_by_str = cols[ordered_by_field]
        if 'order[0][dir]' in request.GET:
            sort_dir = request.GET['order[0][dir]']
            logger.info('Sort Dir {}'.format(sort_dir))
            if sort_dir == 'desc':
                order_by_str = '-{0}'.format(cols[ordered_by_field])

        logger.info('data will be sorted with order_by_str={0}'.format(order_by_str))
        events = events.order_by(order_by_str)

        if length == -1:
            logger.info('length={0}, start={1}, Show ALL'.format(length, start))
            serializer = StreamIdEventDataSerializer(events, many=True, stream=stream)
        else:
            page_num = int(start / length) + 1
            logger.info('length={0}, start={1}, page_num={2}'.format(length, start, page_num))
            p = Paginator(events, length)
            page = p.page(page_num)
            serializer = StreamIdEventDataSerializer(page.object_list, many=True, stream=stream)

        result = {}
        if 'sEcho' in request.GET:
            result['sEcho'] = request.GET['sEcho']

        if 'draw' in request.GET:
            result["draw"] = request.GET['draw']
        result["recordsTotal"] = events.count()
        result["recordsFiltered"] = events.count()
        result["data"] = []
        for item in serializer.data:
            row = {
                'timestamp': item['timestamp'],
                'extra_data': str(item['extra_data'])
            }
            result['data'].append(row)

        return Response(result)

    def list(self, request, *args, **kwargs):
        """
        Get list of streams used by active devices.

        - Use `?all=1` to list all streams (including active and archived devices)
        - Use `?archived=1` to only list streams from archived devices
        """
        return super(APIStreamIdViewSet, self).list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """
        Create a new Stream ID.
        If no device specified, create a virtual stream for the project
        """
        return super(APIStreamIdViewSet, self).create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """
        Staff Only.
        """
        return super(APIStreamIdViewSet, self).update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """
        Staff Only.
        """
        return super(APIStreamIdViewSet, self).partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Staff Only.
        Delete a Stream.
        """
        if not request.user.is_staff:
            return Response({'error': 'Restricted Access. Contact Arch'}, status=status.HTTP_400_BAD_REQUEST)
        return super(APIStreamIdViewSet, self).destroy(request, *args, **kwargs)
