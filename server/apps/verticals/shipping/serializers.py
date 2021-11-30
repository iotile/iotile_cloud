import datetime
import logging

from rest_framework import serializers

from apps.datablock.models import DataBlock, get_block_id
from apps.org.models import Org
from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.streamdata.serializers import StreamDataSerializer
from apps.utils.data_helpers.manager import DataManager
from apps.utils.iotile.variable import SYSTEM_VID, USER_VID
from apps.utils.timezone_utils import convert_to_utc, str_to_dt_utc, str_utc

from .utils.org_quality_report import TripOrgQualityReport
from .utils.project_status_report import TripProjectStatusReport

logger = logging.getLogger(__name__)

_variable_map = {
    'Shocks': USER_VID['ACCEL'],
    'Pressure': USER_VID['PRESSURE'],
    'Relative Humidity': USER_VID['REL_HUMIDITY'],
    'Temperature': USER_VID['TEMP'],
    'Summary': SYSTEM_VID['TRIP_SUMMARY'],
}


class TripSummaryReportSerializer(serializers.ModelSerializer):
    """Serializer used to report the Project Trips Summary Table"""
    config = serializers.SerializerMethodField()
    results = serializers.SerializerMethodField()

    _report = None

    class Meta:
        model = Project
        fields = ('id', 'name', 'slug', 'config', 'results')

    def __init__(self, *args, **kwargs):
        if len(args):
            project = args[0]
            if project:
                self._report = TripProjectStatusReport(project)
                if self._report:
                    self._report.analyze()
        super(TripSummaryReportSerializer, self).__init__(*args, **kwargs)

    def get_results(self, obj):
        if self._report:
            return [obj.to_representation() for slug, obj in self._report.results.items()]
        return {}

    def get_config(self, obj):
        if self._report:
            return self._report.config
        return {}


class TripOrgQualityReportSerializer(serializers.ModelSerializer):
    """Serielizer used to report the Organization Quality Report Table"""
    config = serializers.SerializerMethodField()
    count = serializers.SerializerMethodField()
    results = serializers.SerializerMethodField()

    _quality = None

    class Meta:
        model = Org
        fields = ('id', 'name', 'slug', 'config', 'count', 'results')

    def __init__(self, *args, **kwargs):
        if len(args):
            project = args[0]
            if project:
                self._quality = TripOrgQualityReport(project)
                if self._quality:
                    self._quality.analyze()
        super(TripOrgQualityReportSerializer, self).__init__(*args, **kwargs)

    def get_count(self, obj):
        if self._quality:
            return len(self._quality.results.keys())
        return 0

    def get_results(self, obj):
        if self._quality:
            return [obj.to_representation() for slug, obj in self._quality.results.items()]
        return {}

    def get_config(self, obj):
        if self._quality:
            return self._quality.config
        return {}


class ShippingTripSetupSerializer(serializers.ModelSerializer):
    """Serializer (empty) to take as argument to setup a new trip"""

    class Meta:
        model = Device
        fields = ('slug',  )
        read_only_fields = ('slug', )


class TripArchiveSerializer(serializers.ModelSerializer):
    """Serializer to take arguments to archive a trip"""
    _pid = None
    device = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    org = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    pid = serializers.SerializerMethodField()
    class Meta:
        model = DataBlock
        fields = ('id', 'slug', 'title', 'description', 'device', 'block', 'org', 'sg',
                  'created_on', 'created_by', 'pid',)
        read_only_fields = ('created_on', 'slug', 'device', 'block', )
        extra_kwargs = {
            'sg': {'write_only': True, 'required': False},
            'created_by': {'write_only': True, 'required': False},
        }

    def create(self, validated_data):
        assert 'device' in self.context
        device = self.context['device']
        new_block_id = get_block_id(device)
        block = DataBlock(block=new_block_id, device=device, **validated_data)
        block.save()
        return block

    def get_pid(self, obj):
        if self._pid:
            return str(self._pid)
        return ''

    def set_pid(self, pid):
        self._pid = pid


class ShippingTripInfoSerializerMixin(object):

    def get_data_mask(self, obj):
        """
        :return: Dict object if a mask has been set:
                 {'start': '<datetime_str>', 'end': '<datetime_str>'}.
                 None if not set
        """
        mask_stream_slug = obj.get_stream_slug_for(SYSTEM_VID['DEVICE_DATA_MASK'])
        if mask_stream_slug:
            event = DataManager.filter_qs('event', stream_slug=mask_stream_slug).last()
            if event:
                assert ('start' in event.extra_data)
                assert ('end' in event.extra_data)
                return {
                    'start': event.extra_data.get('start'),
                    'end': event.extra_data.get('end'),
                }
        return None

    def get_streams(self, obj):
        """

        :param obj: Device or DataBlock
        :return: streams payload
        """
        streams = list()

        streams.append({
            'type': 'event',
            'label': 'Shocks',
            'stream': str(obj.get_stream_slug_for(_variable_map['Shocks']))
        })
        for key in ['Pressure', 'Relative Humidity', 'Temperature']:
            streams.append({
                'type': 'data',
                'label': key,
                'stream': str(obj.get_stream_slug_for(_variable_map[key]))
            })
        streams.append({
            'type': 'event',
            'label': 'Summary',
            'stream': str(obj.get_stream_slug_for(_variable_map['Summary']))
        })

        return streams

    def get_trip_date_range(self, obj):
        """
        Figure out the trip Start and End times:

        1. Check for TripStart and Trip End
        2. Check if TripMask is set. If so, use that (if within trip start/end)

        :param obj: Device or DataBlock
        :return: trip_data_range payload
        """
        original_ts_start = original_ts_end = None
        actual_ts_start = actual_ts_end = None
        start_data = end_data = None
        data_was_masked = False

        # Search for actual 'trip start' and 'trip end' events (POD 1M)
        start_trip_stream_slug = obj.get_stream_slug_for(SYSTEM_VID['TRIP_START'])
        end_trip_stream_slug = obj.get_stream_slug_for(SYSTEM_VID['TRIP_END'])

        qs = DataManager.filter_qs(
            'data',
            stream_slug__in=[start_trip_stream_slug, end_trip_stream_slug]
        ).order_by('streamer_local_id', 'timestamp')

        for d in qs:
            if d.stream_slug == str(start_trip_stream_slug):
                original_ts_start = actual_ts_start = convert_to_utc(d.timestamp)
                start_data = StreamDataSerializer(d).data
            if d.stream_slug == str(end_trip_stream_slug):
                original_ts_end = actual_ts_end = convert_to_utc(d.timestamp)
                end_data = StreamDataSerializer(d).data

        # If not found, set ts_start and ts_end to oldest and newest data respectively.
        # This is for backward compatibility (Actuator)
        if not original_ts_start:
            logger.info('No TripStart data found. Looking for oldest data')
            # For backwards compatibility, if no TRIP_START, look for the oldest Event or Data
            first_event = DataManager.filter_qs(
                'event',
                stream_slug=obj.get_stream_slug_for(_variable_map['Shocks'])
            ).exclude(extra_data__has_key='error').first()
            first_temp = DataManager.filter_qs(
                'data',
                stream_slug=obj.get_stream_slug_for(_variable_map['Temperature'])
            ).first()

            if first_event and first_temp:
                first = first_temp if convert_to_utc(first_temp.timestamp) < first_event.timestamp else first_event
            else:
                first = first_temp or first_event

            if first:
                original_ts_start = actual_ts_start = convert_to_utc(first.timestamp)
            else:
                logger.warning('No TRIP_START or data found')

        if original_ts_start and original_ts_end and original_ts_end < original_ts_start:
            # This is the end of a previous trip. Ignore
            original_ts_end = None

        if not original_ts_end:
            logger.info('No TripEnd data found. Looking for latest data')
            # For backwards compatibility, if no TRIP_END, look for the latest Event or Data
            last_event = DataManager.filter_qs(
                'event',
                stream_slug=obj.get_stream_slug_for(_variable_map['Shocks'])
            ).exclude(extra_data__has_key='error').last()
            last_temp = DataManager.filter_qs(
                'data',
                stream_slug=obj.get_stream_slug_for(_variable_map['Temperature'])
            ).last()

            if last_event and last_temp:
                last = last_temp if convert_to_utc(last_temp.timestamp) > last_event.timestamp else last_event
            else:
                last = last_temp or last_event

            if last:
                original_ts_end = convert_to_utc(last.timestamp)
                # Need to add a second as the /data and /event APIs do not include the ?end= timestamp
                actual_ts_end = original_ts_end + datetime.timedelta(seconds=1)
            else:
                logger.warning('No TRIP_END or data found')

        # Check if the device has a data mask. If so, use instead
        # But mask must be more restricted than the existing range
        mask_data = self.get_data_mask(obj)
        if mask_data:
            if mask_data['start']:
                mask_start = str_to_dt_utc(mask_data['start'])
                if original_ts_start is None or mask_start > original_ts_start:
                    actual_ts_start = mask_start
                    data_was_masked = True
            if mask_data['end']:
                mask_end = str_to_dt_utc(mask_data['end'])
                if original_ts_end is None or mask_end < original_ts_end:
                    actual_ts_end = mask_end
                    data_was_masked = True


        return {
            'original_start': str_utc(original_ts_start) if original_ts_start else None,
            'original_end': str_utc(original_ts_end) if original_ts_end else None,
            'actual_start': str_utc(actual_ts_start) if actual_ts_start else None,
            'actual_end': str_utc(actual_ts_end) if actual_ts_end else None,
            'start_data': start_data,
            'end_data': end_data,
            'masked': data_was_masked,
        }


class ShippingTripInfoSerializer(serializers.ModelSerializer, ShippingTripInfoSerializerMixin):
    """Serializer to get Trip Info (For Active Devices)"""
    org = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    project = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    data_mask = serializers.SerializerMethodField()
    trip_date_range = serializers.SerializerMethodField()
    streams = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = ('slug', 'label', 'org', 'project', 'state',
                  'trip_date_range', 'data_mask', 'streams')


class ShippingArchivedTripInfoSerializer(serializers.ModelSerializer, ShippingTripInfoSerializerMixin):
    """Serializer to get Trip Info (For Archived)"""
    org = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    state = serializers.SerializerMethodField()
    data_mask = serializers.SerializerMethodField()
    trip_date_range = serializers.SerializerMethodField()
    streams = serializers.SerializerMethodField()
    label = serializers.SerializerMethodField()

    class Meta:
        model = DataBlock
        fields = ('slug', 'org', 'state', 'label',
                  'trip_date_range', 'data_mask', 'streams')

    def get_state(self, obj):
        return 'A'

    def get_label(self, obj):
        return obj.title
