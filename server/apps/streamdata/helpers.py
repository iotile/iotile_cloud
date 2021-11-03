import logging
import struct

from django.shortcuts import get_object_or_404

from apps.stream.models import StreamId
from apps.project.models import Project
from apps.physicaldevice.models import Device
from apps.utils.iotile.variable import ENCODED_STREAM_VALUES
from apps.streamfilter.cache_utils import cached_serialized_filter_for_slug
from apps.streamfilter.process import FilterHelper

from .models import StreamData
from .utils import get_stream_mdo, get_stream_input_mdo

# Get an instance of a logger
logger = logging.getLogger(__name__)


class StreamDataBuilderHelper(object):
    _streams = {}
    _has_access = {}

    def __init__(self):
        self._streams = {}
        self._has_access = {}

    def add_stream_to_cache(self, key, stream=None):
        if key not in self._streams:
            if not stream:
                try:
                    stream = StreamId.objects.get(slug=key)
                except StreamId.DoesNotExist:
                    stream = None

            logger.info('>>> Adding stream for {}'.format(key))
            self._streams[key] = stream

    def _cast(self, format, int_value):
        # We assume the streamer report parser is unpacking as Long
        # So, we can skip any processing if the stream value format is long
        # We also skip if the format is auto, as that represents non-report
        # values that could be int or float, and we are letting python handle
        # them
        if format == 'auto' or format == '<L':
            value = int_value
        else:
            try:
                raw_value = struct.pack('<L', int(int_value))
                (value,) = struct.unpack(format, raw_value)
            except struct.error as e:
                # TODO: Figure out what to do here
                logger.error(str(e) + ' ===> {}'.format(int_value))
                value = int_value

        # HACK: For now, ensure number fits within 31 bits (IntegerField)
        # TODO: Remove hack once we migrate to a 64bit int_value
        #       It is now 64bit, but we need to test before removing this
        if value > 0x7fffffff:
            value = 0x7fffffff
        elif value < -0x7fffffff:
            value = -0x7fffffff

        return value

    def _cast_stream_value(self, stream, int_value):
        # We assume the data.int_value is always stored in unsigned long
        return self._cast(stream.raw_value_format, int_value)

    def add_stream(self, stream):
        self.add_stream_to_cache(stream.slug, stream)

    def get_cached_streams(self):
        return [self._streams[key] for key in self._streams.keys()]

    def convert_to_internal_value(self, stream_data):
        """
        New Scheme Only Streams with an input_unit will be processed.
        For backwards compatibility, streams with no input_unit will
        keep stream_data.value as None

        If input unit set, then
        value = stream.mdo?stream.mdo|var.mdo -> input_unit.mdo

        :param stream_data:
        :return: stream_data with a value set
        """
        stream = self._streams[stream_data.stream_slug]

        if stream:

            int_value = stream_data.int_value
            assert isinstance(int_value, int)

            if stream.is_encoded > 0:
                if int_value == ENCODED_STREAM_VALUES['BEGIN']:
                    # Packet begins
                    logger.debug('{0}::{1}:: Packet begins at {2}'.format(stream.slug, stream_data.incremental_id, stream_data.device_timestamp))
                    stream_data.type = 'P-0'
                elif int_value == ENCODED_STREAM_VALUES['END']:
                    # Packet ends
                    logger.debug('{0}::{1}:: Packet ends at {2}'.format(stream.slug, stream_data.incremental_id, stream_data.device_timestamp))
                    stream_data.type = 'P-1'
                else:
                    # Add to packet
                    logger.debug('{0}::{1}:: Packet element  at {2}'.format(stream.slug, stream_data.incremental_id, stream_data.device_timestamp))
                    stream_data.type = 'P-E'
            else:
                value = self._cast_stream_value(stream, int_value)

                stream_mdo = get_stream_mdo(stream)
                value = stream_mdo.compute(value)

                input_mdo = get_stream_input_mdo(stream)

                if input_mdo:
                    stream_data.value = input_mdo.compute(value)
                    stream_data.type = 'ITR'
                else:
                    stream_data.value = value
                    stream_data.type = 'Num'
                assert (isinstance(stream_data.value, float))
        else:
            if stream_data.value == None:
                stream_data.value = float(stream_data.int_value)

        return stream_data

    @classmethod
    def get_firehose_payload(cls, stream_data):
        payload = {
            'stream_slug': stream_data.stream_slug,
            'project_slug': stream_data.project_slug,
            'device_slug': stream_data.device_slug,
            'variable_slug': stream_data.variable_slug,
            'type': stream_data.type,
            'dirty_ts': stream_data.dirty_ts,
            'status': stream_data.status,
            'timestamp': stream_data.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')
        }
        if stream_data.device_timestamp is not None:
            payload['device_timestamp'] = stream_data.device_timestamp
        if stream_data.int_value is not None:
            payload['int_value'] = stream_data.int_value
        if stream_data.value is not None:
            payload['value'] = stream_data.value
        if stream_data.streamer_local_id is not None:
            payload['streamer_local_id'] = stream_data.streamer_local_id
        return payload

    def check_if_stream_is_enabled(self, slug):
        self.add_stream_to_cache(slug)
        if self._streams[slug]:
            return self._streams[slug].enabled
        else:
            # StreamData is not associated with a StreamId
            return True

    def build_data_obj(self, *args, **kwargs):
        stream_data = StreamData(**kwargs)
        # NOTE: bulk_create operations will NOT call save() so we need to manually set
        # project_slug, device_slug and variable_slug
        stream_data.deduce_slugs_from_stream_id()

        self.add_stream_to_cache(stream_data.stream_slug)

        self.convert_to_internal_value(stream_data)

        # self.log(stream_data)
        return stream_data

    def process_serializer_data(self, item, user_slug=None):
        # print('serializing: {}'.format(item))
        if not self.check_if_stream_is_enabled(item['stream_slug']):
            return None

        data = self.build_data_obj(**item)

        stream_slug = item['stream_slug']
        # Filter information is cached to avoid the multiple queries to form a filter
        this_filter = cached_serialized_filter_for_slug(stream_slug)
        if 'empty' not in this_filter:
            filter_helper = FilterHelper(skip_dynamo_logs=True)
            filter_helper.process_filter(event, this_filter, user_slug=user_slug)
        return data

    def user_has_write_access(self, stream_data, user):
        """
        Check if user has access to the stream
        Because we allow data to be uploaded without a Stream,
        use the Project and Device to determine access

        :param stream_data: StreamData object
        :param user: User object
        :return: True if user has access to stream
        """
        project_slug = stream_data.project_slug
        device_slug = stream_data.device_slug
        if project_slug in self._has_access and device_slug in self._has_access:
            return self._has_access[project_slug] and self._has_access[device_slug]

        if project_slug not in self._has_access:
            project = get_object_or_404(Project, slug=project_slug)
            assert project.slug == project_slug
            self._has_access[project_slug] = project.org.has_permission(user, 'can_create_stream_data')

        if device_slug not in self._has_access:
            if device_slug != 'd--0000-0000-0000-0000':
                device = get_object_or_404(Device, slug=device_slug)
                self._has_access[device_slug] = device.org.has_permission(user, 'can_create_stream_data')
            else:
                self._has_access[device_slug] = True

        return self._has_access[project_slug] and self._has_access[device_slug]

    def process_stream_filters(self, data_entries, user):
        logger.info('Checking {} data entries for filters'.format(len(data_entries)))

        all_stream_filters = {}
        for entry in data_entries:
            if entry.stream_slug not in all_stream_filters:
                # "expensive" call, call once for each stream in the report
                all_stream_filters[entry.stream_slug] = cached_serialized_filter_for_slug(entry.stream_slug)

        filter_helper = FilterHelper()
        filter_helper.process_filter_report(data_entries, all_stream_filters, user_slug=user.slug)

    def log(self, stream_data):
        logger.info('{0} ==> {1} : {2} - {3}'.format(
            stream_data.stream_slug, stream_data.timestamp, stream_data.int_value, stream_data.value
        ))
