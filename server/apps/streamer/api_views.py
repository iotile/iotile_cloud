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

from iotile_cloud.utils.gid import IOTileDeviceSlug

from apps.utils.rest.custom_serializers import MultiSerializerViewSetMixin
from apps.utils.rest.exceptions import ApiIllegalFilterOrTargetException
from apps.utils.rest.permissions import IsStaffOrReadOnly
from apps.utils.timezone_utils import convert_to_utc, force_to_utc
from apps.utils.uuid_utils import validate_uuid

from .models import *
from .msg_pack import MessagePackRenderer, Python2CompatMessagePackParser
from .serializers import *
from .tasks import ReportUploaderAndProcessScheduler

logger = logging.getLogger(__name__)


class StreamerApiFilter(django_filters.rest_framework.FilterSet):
    device = django_filters.CharFilter(method='filter_by_device')
    class Meta:
        model = Streamer
        fields = ['device', 'selector', 'slug']

    def filter_by_device(self, queryset, name, value):
        try:
            device_slug = IOTileDeviceSlug(value)
        except ValueError as e:
            raise ApiIllegalFilterOrTargetException('Illegal device format. {}'.format(e))
        device = get_object_or_404(Device, slug=device_slug)
        return queryset.filter(device=device)


class StreamerReportApiFilter(django_filters.rest_framework.FilterSet):
    # Datetime format in UTC: `2018-01-01T01:00:00Z`
    start = django_filters.IsoDateTimeFilter(field_name='sent_timestamp', lookup_expr='gte')
    # Datetime format in UTC: `2018-01-01T01:00:00Z`
    end = django_filters.IsoDateTimeFilter(field_name='sent_timestamp', lookup_expr='lt')
    class Meta:
        model = StreamerReport
        fields = ['streamer__slug', 'start', 'end', 'created_by__slug']


class APIStreamerViewSet(viewsets.ModelViewSet):
    """
    Devices have one or more streamers. Each streamer will
    send a streamer report when data is available for that streamer
    and base on its sensor graph.

    list: Get list of all streamers the user has access to.
          Use `?device=` to filter out by device

    retrieve: Get a specific streamer based on its streamer ID.

    report: Get a list of streamer report records for a given streamer.

    """
    lookup_field = 'slug'
    queryset = Streamer.objects.none()
    serializer_class = StreamerSerializer
    permission_classes = (IsStaffOrReadOnly, )
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = StreamerApiFilter

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        if self.request.user.is_staff and self.request.GET.get('staff', ''):
            qs = Streamer.objects.all()
        else:
            qs = Streamer.objects.user_streamer_qs(self.request.user)

        return qs.select_related('device')

    def perform_create(self, serializer):
        # Include the owner attribute directly, rather than from request data.
        instance = serializer.save(created_by=self.request.user)

    @action(methods=['get'], detail=True)
    def report(self, request, slug=None):
        streamer = self.get_object()
        reports = streamer.reports.all().order_by('created_on')
        serializer = StreamerReportSerializer(reports, many=True)
        return Response(serializer.data)


class APIStreamerReportUploadView(MultiSerializerViewSetMixin, viewsets.ModelViewSet):
    queryset = StreamerReport.objects.none()
    serializer_class = StreamerReportSerializer
    permission_classes = (IsAuthenticated, )
    serializer_action_classes = {
        'create': StreamerReportJsonPostSerializer,
        'list': StreamerReportSerializer,
        'retrieve': StreamerReportSerializer,
    }
    parser_classes = (MultiPartParser, FormParser, JSONParser, Python2CompatMessagePackParser,)
    renderer_classes = (JSONRenderer, BrowsableAPIRenderer, MessagePackRenderer,)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = StreamerReportApiFilter

    def get_object(self):
        pk = self.kwargs['pk']
        if not validate_uuid(pk):
            raise ValidationError('Streamer Report ID must be a UUID')

        return super(APIStreamerReportUploadView, self).get_object()

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        if self.request.user.is_staff and self.request.GET.get('staff', ''):
            qs = StreamerReport.objects.all()
        else:
            streamer_qs = Streamer.objects.user_streamer_qs(self.request.user)
            qs = StreamerReport.objects.filter(streamer__in=streamer_qs)

        return qs.select_related('streamer').order_by('created_on')

    def perform_create(self, serializer):
        """
        Handling Timestamps:
        Because the device has no concept of absolute time, we need to do some math
        to convert the device's relative time to absolute datetimes.

        received_dt is the absolute time at which the gateway received the report (as a datetime)
        sent_timestamp is the timestamp when the device sent the report (in seconds)
        point_timestamp is the timestamp of a reading (in seconds)

        Estimate the UTC time when this device was turned on
            base_dt = received_dt - datetime.timedelta(seconds=sent_timestamp)
            reading_dt = base_dt + datetime.timedelta(seconds=point_timestamp)

        """
        if 'timestamp' not in self.request.GET:
            raise ValidationError('Upload function requires a ?timestamp=str argument in UTC format')

        arg_timestamp = self.request.GET.get('timestamp')
        received_dt = force_to_utc(arg_timestamp)
        if not received_dt:
            raise ValidationError('Upload function requires a ?timestamp=str argument in UTC format')
        logger.info('timestamp: arg = {0}, dt = {1}'.format(arg_timestamp, convert_to_utc(received_dt)))

        if 'file' in self.request.data:
            # API can accept a file as upload. Used for device stream reports
            filename = str(self.request.data['file'])
            fp = self.request.data['file']
            logger.debug('[APIStreamerReportUploadView] filename: {}'.format(filename))

            report_processor = ReportUploaderAndProcessScheduler(fp=fp, received_dt=received_dt, request=self.request)

            resp, streamer_report = report_processor.process(serializer=serializer, filename=filename)
            return resp
        else:
            # API can also accept normal serializer
            instance = serializer.save(created_by=self.request.user)
            logger.error('Under construction')
            print('Under construction: upload without attached file')

    @swagger_auto_schema(
        request_body=StreamerReportJsonPostSerializer,
        responses={
            201: '{"Count": num}',
        },
        manual_parameters=[
            openapi.Parameter(
                name='timestamp', in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Timestamp at the moment the file is upload. Format e.g. 2018-01-01T10:00:00.000Z",
                required=True
            ),
        ]
    )
    def create(self, request, *args, **kwargs):
        """
        Upload a Streamer Report file and data payload for processing.

        Actual file should be attached using a multipart form:

        'Content-Type: multipart/form-data'

        Supported files:
        - `.bin`: For iotile coretool based Streamer Report binary files
        - `.json`: For JSON based virtual Streamer Reports

        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if 'file' not in self.request.data:
            return Response({'error': 'missing request.data[\'file\']'}, status=status.HTTP_400_BAD_REQUEST)

        if 'timestamp' not in self.request.GET:
            return Response({'error': 'missing timestamp argument'}, status=status.HTTP_400_BAD_REQUEST)

        count = self.perform_create(serializer)
        return Response({'count': count}, status=status.HTTP_201_CREATED)
