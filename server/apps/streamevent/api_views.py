# Modules needed to execute back-end jobs requested by server
from botocore.exceptions import ClientError

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

import django_filters
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer
from rest_framework.response import Response

from apps.stream.models import StreamId
from apps.streamer.msg_pack import MessagePackParser, MessagePackRenderer
from apps.utils.aws.s3 import download_gzip_blob, download_json_data_as_object, upload_json_data_from_object
from apps.utils.data_mask.mask_utils import get_data_mask_date_range_for_slug
from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.objects.utils import get_device_or_block, get_object_by_slug
from apps.utils.rest.exceptions import ApiIllegalFilterOrTargetException, ApiIllegalPkException
from apps.utils.rest.pagination import LargeResultsSetPagination
from apps.utils.timezone_utils import str_to_dt_utc

from .helpers import StreamEventDataBuilderHelper
from .models import *
from .serializers import *

user_model = get_user_model()

# Get an instance of a logger
logger = logging.getLogger(__name__)


class StreamEventDataFilter(django_filters.rest_framework.FilterSet):
    # Datetime format in UTC: `2018-01-01T01:00:00Z`
    start = django_filters.IsoDateTimeFilter(field_name='timestamp', lookup_expr='gte')
    # Datetime format in UTC: `2018-01-01T01:00:00Z`
    end = django_filters.IsoDateTimeFilter(field_name='timestamp', lookup_expr='lt')
    id = django_filters.RangeFilter(field_name='id')
    streamer_id = django_filters.RangeFilter(field_name='streamer_local_id')
    streamer_ts = django_filters.RangeFilter(field_name='device_timestamp')
    # For the moment, we keep the _0 and _1 suffixes for backward compatibility
    id_0 = django_filters.NumberFilter(field_name='id', lookup_expr='gte')
    id_1 = django_filters.NumberFilter(field_name='id', lookup_expr='lte')
    streamer_id_0 = django_filters.NumberFilter(field_name='streamer_local_id', lookup_expr='gte')
    streamer_id_1 = django_filters.NumberFilter(field_name='streamer_local_id', lookup_expr='lte')
    lastn = django_filters.NumberFilter(method='get_lastn')

    class Meta:
        model = StreamEventData
        fields = ['timestamp']

    def get_lastn(self, queryset, name, value):
        if value < 1:
            raise ValidationError('lastn must be greater than 0')
        elif value > 100000:
            raise ValidationError('lastn limit is 100000')

        n = queryset.count()
        if value > n:
            # queryset doesn't support negative indexing
            qs = queryset.order_by('timestamp')
        else:
            qs = queryset.order_by('timestamp')[n-value:]

        return qs


class APIStreamEventDataViewSet(viewsets.ModelViewSet):
    """
    Get all StreamEventData.

    Similar to StreamData, but for data that cannot be represented as
    a numerical value. Instead, this data represents events with unstructured
    data.

    create: Staff Only.
    destroy: Staff Ony.
    destroy: Staff Only.

    """
    queryset = StreamEventData.objects.none()
    serializer_class = StreamEventDataSerializer
    permission_classes = (IsAuthenticated,)
    pagination_class = LargeResultsSetPagination
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = StreamEventDataFilter
    parser_classes = (JSONParser, MessagePackParser,)
    renderer_classes = (JSONRenderer, BrowsableAPIRenderer, MessagePackRenderer,)

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        qs = None
        obj = None
        use_mask = self.request.GET.get('mask', '') == '1'
        filter_value = self.request.GET.get('filter', None)
        if filter_value:

            obj_name, obj = get_object_by_slug(filter_value)
            if obj:
                if obj.org and obj.org.has_permission(self.request.user, 'can_read_stream_data'):
                    qs = StreamEventData.objects.filter_by_slug(obj.slug)
            else:
                # Need to specially handle Streams that have no StreamId record
                if obj_name == 'stream':
                    try:
                        stream_slug = IOTileStreamSlug(filter_value)
                        parts = stream_slug.get_parts()
                    except ValueError as e:
                        raise ApiIllegalFilterOrTargetException('Illegal filter argument format (Illegal Stream). {}'.format(e))
                    assert parts and 'device' in parts
                    obj = get_device_or_block(parts['device'])

                    if obj is not None and obj.org and obj.org.has_permission(self.request.user, 'can_read_stream_data'):
                        qs = StreamEventData.objects.filter_by_slug(filter_value)
                    elif obj is None:
                        # If the device is None, this could be a project virtual stream. Check if there is a project
                        _, project = get_object_by_slug(str(parts['project']))
                        if project is not None and project.org and project.org.has_permission(self.request.user, 'can_read_stream_data'):
                            qs = StreamEventData.objects.filter_by_slug(filter_value)

        if qs:
            if use_mask and obj is not None and obj.slug[0] != 'v':
                mask_stream_slug = obj.get_stream_slug_for(SYSTEM_VID['DEVICE_DATA_MASK'])
                mask = get_data_mask_date_range_for_slug(mask_stream_slug)
                if mask and mask['start']:
                    mask_start = str_to_dt_utc(mask['start'])
                    qs = qs.filter(timestamp__gte=mask_start)
                if mask and mask['end']:
                    mask_end = str_to_dt_utc(mask['end'])
                    qs = qs.filter(timestamp__lt=mask_end)

        if qs:
            # Filter out all encoding errors
            with_errors = self.request.user.is_staff and self.request.GET.get('with_errors', '')
            if with_errors:
                return qs
            return qs.exclude(extra_data__has_key='error')

        return StreamEventData.objects.none()

    def get_object(self):
        """
        Get object if Staff

        """
        try:
            id = int(self.kwargs['pk'])
        except Exception:
            raise ApiIllegalPkException

        obj = get_object_or_404(StreamEventData, pk=id)

        if self.request.user.is_staff:
            return obj

        stream = get_object_or_404(StreamId, slug=obj.stream_slug)
        if stream.org and stream.org.has_permission(self.request.user, 'can_create_stream_data'):
            return obj

        raise PermissionDenied

    def perform_create(self, serializer):
        helper = StreamEventDataBuilderHelper()
        entries = []
        many = isinstance(serializer.validated_data, list)

        if many:
            count = 0
            for item in serializer.validated_data:
                event = helper.process_serializer_data(item, user_slug=self.request.user.slug)
                if event and helper.user_has_write_access(event=event, user=self.request.user):
                    entries.append(event)
                    count += 1
                else:
                    if event:
                        raise PermissionDenied('Not allowed to upload to {0}'.format(event.stream_slug))
                    raise PermissionDenied('Stream not enabled {0}'.format(item['stream_slug']))
            logger.info('Committing batch of {0} data event entries'.format(count))
            if count:
                StreamEventData.objects.bulk_create(entries)
                return {'count': count}
        else:
            event = helper.process_serializer_data(serializer.validated_data, user_slug=self.request.user.slug)
            if event and helper.user_has_write_access(event=event, user=self.request.user):
                event.save()
                s = self.serializer_class(event)
                return s.data
            else:
                raise PermissionDenied('Not allowed to upload to {0}'.format(event.stream_slug))

    def perform_update(self, serializer):

        event = serializer.instance
        stream = get_object_or_404(StreamId, slug=event.stream_slug)
        if not (stream.org and stream.org.has_permission(self.request.user, 'can_create_stream_data')):
            raise PermissionDenied('User is not allowed to PATCH {0}'.format(event.stream_slug))

        data = None
        if 'data' in serializer.validated_data:
            data = serializer.validated_data.pop('data')

        event = serializer.save()
        if data:
            # Also set s3 path from now()
            event.set_s3_key_path()

            bucket = event.s3bucket
            key = event.s3key
            success = upload_json_data_from_object(bucket=bucket, key=key, data=data)
            if not success:
                raise ValidationError('Unable to upload Event Data')

            event.save()

    def create(self, request, *args, **kwargs):
        """
        Staff Only. Contact us to learn how to upload data
        """
        many = isinstance(request.data, list)
        serializer = self.get_serializer(data=request.data, many=many)
        serializer.is_valid(raise_exception=True)
        data = self.perform_create(serializer)
        return Response(data, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(
        method='get',
        responses={
            200: 'Raw JSON data file',
        }
    )
    @action(methods=['get'], detail=True)
    def data(self, request, pk=None):
        """
        Get actual event data as JSON
        """

        event = self.get_object()
        if not event.has_raw_data:
            return Response({'error': 'Event has no data'}, status=status.HTTP_404_NOT_FOUND)

        if event.ext == 'json':
            try:
                data = download_json_data_as_object(bucket=event.s3bucket, key=event.s3key)
            except ClientError as e:
                return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)
            return Response(data)
        elif event.ext == 'json.gz':
            try:
                decompressed_file = download_gzip_blob(bucket=event.s3bucket, key=event.s3key)
                data = json.loads(decompressed_file, encoding='utf-8')
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)
            return Response(data)
        else:
            return Response({'error': 'Event has no data'}, status=status.HTTP_404_NOT_FOUND)

    @swagger_auto_schema(
        method='get',
        responses={
            200: 'URL to data file',
        }
    )
    @action(methods=['get'], detail=True)
    def url(self, request, pk=None):
        """
        Get a signed URL to download file directly
        """

        event = self.get_object()
        return Response({"url": event.url})

    @swagger_auto_schema(manual_parameters=[
        openapi.Parameter(
            name='filter', in_=openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            description="Use a device slug or stream slug to filter",
            required=True
        ),
        openapi.Parameter(
            name='start', in_=openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            description="Show data from this datetime"
        ),
        openapi.Parameter(
            name='end', in_=openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            description="Show data up to this datetime"
        ),
    ])
    def list(self, request, *args, **kwargs):
        return super(APIStreamEventDataViewSet, self).list(request, args)


class APIStreamEventUploadViewSet(viewsets.ModelViewSet):
    queryset = StreamEventData.objects.all()
    serializer_class = StreamEventDataRawUploadSerializer
    permission_classes = (IsAuthenticated, )
    parser_classes = (MultiPartParser, FormParser, JSONParser, MessagePackParser,)
    http_method_names = ['post', 'head']

    def perform_create(self, serializer):
        """
        This method takes care of this API's payload and file content.
        The payload is used to create a StreamEventData record while
        the file is uploaded to S3 and kye is added to this new event
        """

        if 'file' in self.request.data:
            # API can accept a file as upload. Used for device stream reports
            fp = self.request.data['file']

            helper = StreamEventDataBuilderHelper()
            event = helper.process_serializer_data(serializer.validated_data)
            if event and helper.user_has_write_access(event=event, user=self.request.user):
                event = helper.manual_file_upload(event, fp)
                event.save()
                s = self.serializer_class(event)
                return s.data
            else:
                raise PermissionDenied('Not allowed to upload to {0}'.format(event.stream_slug))
        else:
            # API can also accept normal serializer
            instance = serializer.save(created_by=self.request.user)
            logger.error('Under construction')
            print('Under construction: upload without attached file')

    @swagger_auto_schema(
        request_body=StreamEventDataRawUploadSerializer,
        responses={
            201: '{"Count": num}',
        }
    )
    def create(self, request, *args, **kwargs):
        """
        Upload a raw data file, and create a StreamEvent for it.

        Actual file should be attached using a multipart form:

        'Content-Type: multipart/form-data'

        Supported files:
        - `.json`: JSON file
        - `.gzip_json`: For zipped JSON file

        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if 'file' not in self.request.data:
            return Response({'error': 'missing request.data[\'file\']'}, status=status.HTTP_400_BAD_REQUEST)

        data = self.perform_create(serializer)
        return Response(data, status=status.HTTP_201_CREATED)
