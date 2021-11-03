# Modules needed to execute back-end jobs requested by server

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404

import django_filters
from rest_framework import viewsets
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ParseError, ValidationError

from rest_pandas import PandasSimpleView, PandasView
from rest_pandas import PandasCSVRenderer, PandasJSONRenderer, PandasTextRenderer

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

from iotile_cloud.utils.gid import IOTileStreamSlug

from apps.utils.aws.kinesis import send_to_firehose
from apps.utils.rest.pagination import LargeResultsSetPagination
from apps.utils.rest.exceptions import ApiIllegalPkException
from apps.utils.rest.exceptions import ApiIllegalFilterOrTargetException
from apps.utils.objects.utils import get_object_by_slug, get_device_or_block
from apps.utils.timezone_utils import str_to_dt_utc
from apps.stream.models import StreamId
from apps.utils.data_mask.mask_utils import get_data_mask_date_range_for_slug
from apps.utils.iotile.variable import SYSTEM_VID


from .serializers import *
from .models import *
from .helpers import StreamDataBuilderHelper
from .utils import get_stream_output_mdo

user_model = get_user_model()

# Get an instance of a logger
logger = logging.getLogger(__name__)


def update_filter_with_mask_data_range(qfilter, obj=None):
    """
    Resolve conflicts between any given filter and the device data mask. If

    :param qfilter: Dict with any existing filter. A filter may come from an API parameter (self.request.GET).
    :param obj: StreamId, Device or DataBlock to get data mask with
    :return: Dictionary with 'start' and 'end' set as datetimes if set, and accounting for mask
    """
    result = {}

    if 'start' in qfilter:
        result['start'] = str_to_dt_utc(qfilter['start'])
    if 'end' in qfilter:
        result['end'] = str_to_dt_utc(qfilter['end'])

    if obj:
        mask_stream_slug = obj.get_stream_slug_for(SYSTEM_VID['DEVICE_DATA_MASK'])
        mask = get_data_mask_date_range_for_slug(mask_stream_slug)
        if mask and mask['start']:
            mask_start = str_to_dt_utc(mask['start'])
            if 'start' in result:
                if mask_start > result['start']:
                    result['start'] = mask_start
            else:
                result['start'] = mask_start

        if mask and mask['end']:
            mask_end = str_to_dt_utc(mask['end'])
            if 'end' in result:
                if mask_end < result['end']:
                    result['end'] = mask_end
            else:
                result['end'] = mask_end

    return result


class StreamDataFilter(django_filters.rest_framework.FilterSet):
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
        model = StreamData
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


class APIStreamDataFrameViewSet(PandasSimpleView):
    """
    Get all StreamData as a data frame in CSV, JSON or TXT form.

    This is a faster API to get the stream data timeseries, and only returns:

    { stream_slug, timestamp, value }

    This API requires a filter argument, in the form of:

    * `/api/v1/data/?filter=d--0000-0000-0000-aaaa`  to show all data for a given device
    * `/api/v1/data/?filter=b--0001-0000-0000-aaaa`  to show all data for a given data block (Archive)
    * `/api/v1/data/?filter=s--0000-0001--0000-0000-0000-aaaa--5001`  to show all data for a given stream

    Use `start=<datetime>` and/or `end=<datetime>` to set a data range. Datetime format in UTC: `2018-01-01T01:00:00Z`

    Use `apply_mdo=1` to automatically apply MDO based on stream's output units. Otherwise, always returning storage value

    Use `extended=1` to include additional columns: device_timestamp, streamer_local_id

    Use `pivot=1` to get data in pivot form, with each stream as a column.
    Use `pivot=1&stats=1` to return stats in pivot form

    Use `mask=1` if you want the datatime range to be within the device data mask (if set)

    """
    queryset = StreamData.objects.all()
    renderer_classes = [PandasCSVRenderer, PandasJSONRenderer, PandasTextRenderer]
    permission_classes = (IsAuthenticated,)

    def get_data(self, request, *args, **kwargs):
        qs = StreamData.df_objects.none()

        extended = self.request.GET.get('extended', '') == '1'
        apply_mdo = self.request.GET.get('apply_mdo', '') == '1'
        use_mask = self.request.GET.get('mask', '') == '1'
        filter_value = self.request.GET.get('filter', None)
        range_filter = {}
        stream_set = set()
        obj = None
        obj_name = ''
        if filter_value:
            obj_name, obj = get_object_by_slug(filter_value)
            if obj:
                if obj and obj.org and obj.org.has_permission(self.request.user, 'can_read_stream_data'):
                    if obj_name == 'stream':
                        stream_set.add(obj.slug)
                    elif obj_name == 'device':
                        for stream in StreamId.objects.filter(device=obj, block__isnull=True):
                            stream_set.add(stream.slug)
                    elif obj_name == 'datablock':
                        for stream in StreamId.objects.filter(block=obj):
                            stream_set.add(stream.slug)
                    if len(stream_set):
                        qs = StreamData.df_objects.filter(stream_slug__in=[s for s in stream_set])

                    range_filter = update_filter_with_mask_data_range(self.request.GET, obj=obj if use_mask else None)

            else:
                # Need to specially handle Streams that have no StreamId record
                if obj_name == 'stream':
                    try:
                        stream_slug = IOTileStreamSlug(filter_value)
                        parts = stream_slug.get_parts()
                    except ValueError as e:
                        raise ApiIllegalFilterOrTargetException('Illegal filter argument format (Illegal Stream). {}'.format(e))
                    assert parts and 'device' in parts
                    device = get_device_or_block(parts['device'])
                    if device and device.org and device.org.has_permission(self.request.user, 'can_read_stream_data'):
                        qs = StreamData.df_objects.filter(stream_slug=filter_value)

                    range_filter = update_filter_with_mask_data_range(self.request.GET)


        if 'start' in range_filter and range_filter['start']:
            qs = qs.filter(timestamp__gte=range_filter['start'])
        if 'end' in range_filter and range_filter['end']:
            qs = qs.filter(timestamp__lt=range_filter['end'])

        pivot= obj and self.request.GET.get('pivot', '') == '1'
        if pivot:
            try:
                df = qs.values_list('timestamp').distinct().to_timeseries(
                    index='timestamp',
                    pivot_columns='stream_slug',
                    values='value',
                    storage='long'
                )
            except Exception as e:
                raise ParseError(e)
        else:
            try:
                if obj:
                    cols = ['value', 'stream_slug']
                else:
                    cols = ['int_value', 'stream_slug']
                if extended:
                    cols += ['device_timestamp', 'streamer_local_id']

                df = qs.to_timeseries(cols, index='timestamp')
            except Exception as e:
                raise ParseError(e)

        # Apply MDO per stream if needed
        if apply_mdo and not df.empty:
            if pivot:
                streams = StreamId.objects.filter(slug__in=[str(col) for col in df])
                for stream in streams:
                    mdo = get_stream_output_mdo(stream)
                    if mdo:
                        try:
                            # Apply MDO for whole column, representing single stream (as it is a pivot)
                            df[stream.slug] = df[stream.slug].apply(lambda x: mdo.compute(x))
                        except Exception as e:
                            raise ParseError(e)

                if 'stats' in self.request.GET and self.request.GET['stats'] == '1':
                    # Optionally compute stats instead
                    try:
                        df = df.agg(['count', 'sum', 'mean', 'std', 'min', 'median', 'max'])
                    except Exception as e:
                        raise ParseError(e)
            else:
                streams = StreamId.objects.filter(slug__in=stream_set)
                for stream in streams:
                    mdo = get_stream_output_mdo(stream)
                    if mdo:
                        try:
                            # Selectively apply MDO to rows for given stream
                            df['value'] = df.apply(lambda x: mdo.compute(x['value']) if x['stream_slug'] == stream.slug else x['value'], axis=1)
                        except Exception as e:
                            raise ParseError(e)

        return df


class APIStreamDataViewSet(viewsets.ModelViewSet):
    """
    Get all StreamData.
    
    * StreamData is the data collected from an IOTile Device over time. 
    * It is associated with a Stream, which represents the given output (Variable) for a given Device

    create: Staff Only.
    destroy: Staff Ony.
    destroy: Staff Only.

    """
    queryset = StreamData.objects.none()
    serializer_class = StreamDataSerializer
    permission_classes = (IsAuthenticated,)
    pagination_class = LargeResultsSetPagination
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = StreamDataFilter

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        qs = None
        obj = None
        use_mask = self.request.GET.get('mask', '') == '1'
        is_staff = self.request.user.is_staff and self.request.GET.get('staff', '')
        filter_value = self.request.GET.get('filter', None)
        if filter_value:
            if filter_value == 'future' and is_staff:
                # Undocumented feature for Staff to be able to look for anomalies:
                # Data in the future
                return StreamData.objects.filter(timestamp__gte=timezone.now())

            obj_name, obj = get_object_by_slug(filter_value)
            if obj:
                if obj.org and obj.org.has_permission(self.request.user, 'can_read_stream_data'):
                    qs = StreamData.objects.filter_by_slug(obj.slug)
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
                        qs = StreamData.objects.filter_by_slug(filter_value)
                    elif obj is None:
                        # If the device is None, this could be a project virtual stream. Check if there is a project
                        _, project = get_object_by_slug(str(parts['project']))
                        if project is not None and project.org and project.org.has_permission(self.request.user, 'can_read_stream_data'):
                            qs = StreamData.objects.filter_by_slug(filter_value)

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

            return qs

        return StreamData.objects.none()

    def get_object(self):
        """
        Get object if Staff

        """
        try:
            id = int(self.kwargs['pk'])
        except Exception:
            raise ApiIllegalPkException

        obj = get_object_or_404(StreamData, pk=id)

        if self.request.user.is_staff:
            return obj

        raise PermissionDenied

    def perform_create(self, serializer):
        entries = []
        many = isinstance(serializer.validated_data, list)
        helper = StreamDataBuilderHelper()
        if many:
            count = 0
            if not getattr(settings, 'USE_FIREHOSE'):
                logger.debug('Using bulk-create (Production = {0})'.format(getattr(settings, 'PRODUCTION')))
                for item in serializer.validated_data:
                    stream_data = helper.build_data_obj(**item)
                    if stream_data and helper.user_has_write_access(stream_data=stream_data, user=self.request.user):
                        entries.append(stream_data)
                        count += 1
                    else:
                        raise PermissionDenied('User has no access to least some data points')
                if count:
                    helper.process_stream_filters(entries, user=self.request.user)
                    logger.info('Committing batch of {0} data entries'.format(count))
                    StreamData.objects.bulk_create(entries)

            else:
                for item in serializer.validated_data:
                    stream_data = helper.build_data_obj(**item)
                    if stream_data and helper.user_has_write_access(stream_data=stream_data, user=self.request.user):
                        entries.append(StreamDataBuilderHelper.get_firehose_payload(stream_data))
                        count += 1
                    else:
                        raise PermissionDenied('User has no access to least some data points')

                if count:
                    helper.process_stream_filters(entries, user=self.request.user)
                    send_to_firehose(entries, batch_num=490)

            return Response({'count': count}, status=status.HTTP_201_CREATED)

        else:
            stream_data = helper.build_data_obj(**serializer.validated_data)
            if stream_data and helper.user_has_write_access(stream_data=stream_data, user=self.request.user):
                helper.process_stream_filters([stream_data, ], user=self.request.user)
                stream_data.save()
                # helper.log(stream_data)
            else:
                raise PermissionDenied('Not allowed to upload to {0}'.format(stream_data.stream_slug))

            ret_serializer = StreamDataSerializer(stream_data)
            return Response(ret_serializer.data, status=status.HTTP_201_CREATED)


    def create(self, request, *args, **kwargs):
        """
        Staff Only. Contact us to learn how to upload data
        """
        many = isinstance(request.data, list)
        serializer = self.get_serializer(data=request.data, many=many)
        serializer.is_valid(raise_exception=True)
        return self.perform_create(serializer)

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
        return super(APIStreamDataViewSet, self).list(request, args)
