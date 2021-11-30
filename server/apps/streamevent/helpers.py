import logging
import os
import struct

import structpp

from django.shortcuts import get_object_or_404

from rest_framework.exceptions import ValidationError

from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.stream.models import StreamId
from apps.streamfilter.cache_utils import cached_serialized_filter_for_slug
from apps.streamfilter.process import FilterHelper
from apps.utils.aws.s3 import upload_blob, upload_json_data_from_object
from apps.utils.mdo.helpers import MdoHelper

from .models import StreamEventData

# Get an instance of a logger
logger = logging.getLogger(__name__)


class StreamEventDataBuilderHelper(object):
    _streams = {}
    _all_stream_filters = {}
    _has_access = {}

    def __init__(self):
        self._streams = {}
        self._has_access = {}

    def _add_stream(self, stream_slug):
        try:
            stream = StreamId.objects.get(slug=stream_slug)
        except StreamId.DoesNotExist:
            stream = None

        self._streams[stream_slug] = stream

    def get_cached_streams(self):
        return [self._streams[key] for key in self._streams.keys() ]

    def check_if_stream_is_enabled(self, slug):
        if slug not in self._streams:
            self._add_stream(slug)
        if self._streams[slug]:
            return self._streams[slug].enabled
        else:
            # StreamEventData is not associated with a StreamId
            return True

    def _build_stream_event_data(self, *args, **kwargs):
        event = StreamEventData(**kwargs)

        # NOTE: bulk_create operations will NOT call save() so we need to manually set
        # project_slug, device_slug and variable_slug
        event.deduce_slugs_from_stream_id()

        return event

    def process_serializer_data(self, item, user_slug=None):
        if not self.check_if_stream_is_enabled(item['stream_slug']):
            return None

        data = None
        if 'data' in item:
            data = item.pop('data')
        event = self._build_stream_event_data(**item)
        if data:
            # Also set s3 path from now()
            event.set_s3_key_path()

            bucket = event.s3bucket
            key = event.s3key
            success = upload_json_data_from_object(bucket=bucket, key=key, data=data)
            if not success:
                raise ValidationError('Unable to upload Event Data')

        stream_slug = item['stream_slug']
        # Filter information is cached to avoid the multiple queries to form a filter
        this_filter = cached_serialized_filter_for_slug(stream_slug)
        if 'empty' not in this_filter:
            filter_helper = FilterHelper(skip_dynamo_logs=True)
            filter_helper.process_filter(event, this_filter, user_slug=user_slug)
        return event

    def manual_file_upload(self, event, fp):
        filename = str(fp)
        logger.debug('[APIStreamEventUploadView] filename: {}'.format(filename))

        base_format = {
            '.json': 'json',
            '.json.gz': 'json'
        }

        filename_components = os.path.basename(filename).split(os.extsep)
        if len(filename_components) <= 1:
            raise ValidationError('Filename must use file extensions')

        ext = '.' + '.'.join(filename_components[1:])

        if ext not in base_format:
            raise ValidationError('Unsupported extension for Stream Event')

        event.ext = ext[1:]

        # Setup S3 key and bucket
        event.set_s3_key_path()
        bucket = event.s3bucket
        key = event.s3key

        metadata = {
            'base_format': base_format[ext]
        }
        try:
            upload_blob(bucket=bucket, key=key, blob=fp, metadata=metadata)
        except Exception:
            raise ValidationError('Unable to upload Event Data')

        return event

    def user_has_write_access(self, event, user):
        """
        Check if user has access to the stream
        Because we allow data to be uploaded without a Stream,
        use the Device if one exist to check access.
        Use the Project otherwise.
        A device may be 0 for virtual streams and a project
        may be 0 for data blocks, but at least one should be 
        valid if this is a legal slug

        :param event: StreamEventData object
        :param user: User object
        :return: True if user has access to stream
        """
        project_slug = event.project_slug
        device_slug = event.device_slug

        # Get data from cache if it exists
        if device_slug in self._has_access:
            return self._has_access[device_slug]
        if project_slug in self._has_access:
            return self._has_access[project_slug]

        if device_slug not in self._has_access and device_slug != 'd--0000-0000-0000-0000':
            device = get_object_or_404(Device, slug=device_slug)
            self._has_access[device_slug] = device.org.has_permission(user, 'can_create_stream_data')
            return self._has_access[device_slug]

        if project_slug not in self._has_access and project_slug != 'p--0000-0000':
            project = get_object_or_404(Project, slug=project_slug)
            self._has_access[project_slug] = project.org.has_permission(user, 'can_create_stream_data')
            return self._has_access[project_slug]

        return False


class EncodedStreamToEventDataHelper(object):
    """
    Helper class to help create StreamEventData objects from encoded StreamData objects
    """
    _packet = []
    _stream = None
    _decoder = None
    _start = None
    error_count = 0

    def __init__(self, stream):
        assert stream
        self._stream = stream
        assert stream.is_encoded
        var_type = stream.var_type
        assert var_type
        self._decoder = var_type.decoder
        assert self._decoder
        self.error_count = 0

        self._begin(None)

    def _process_transformations(self, value, transform):
        """
        Post process values based on the Decoder's element MDO/Maps
        :param value:
        :param var_type:
        :return:
        """
        if 'map' in transform:
            if str(value) in transform['map']:
                return transform['map'][str(value)]
        if 'mdo' in transform:
            assert len(transform['mdo']) == 3
            mdo = MdoHelper(transform['mdo'][0], transform['mdo'][1], transform['mdo'][2])
            return mdo.compute(value)
        return value

    def _unpack_data(self, end):
        """
        Based on a VarTypeDecoder, create a blob with all data in the packet
        (using the decoder's raw_packet_format), and then unpack using the
        decoder's 'decoding' array.

        Finally, use the same 'decoding' array to get the kay to use for every
        unpacked value, and add it to the event's extra_data JSON field

        :param event: StreamEventData to add extra_data to
        :return: Modified StreamEventData
        """

        # Prepare single data blob

        if len(self._decoder.raw_packet_format) - 1 != len(self._packet):
            msg = '{0}: RawPacketFromat length ({1}={2} - 1) is not the same as packet size ({3})'.format(
                self._start.stream_slug,
                self._decoder.raw_packet_format,
                len(self._decoder.raw_packet_format),
                len(self._packet)
            )
            self.error_count += 1
            return {
                'error': msg,
                'start': self._start.incremental_id,
                'end': end.incremental_id
            }

        values = [point.int_value for point in self._packet]
        try:
            blob = struct.pack(self._decoder.raw_packet_format, *values)
        except Exception as e:
            logger.error(e)
            return {}

        # Now decode using the decoder's packer info for this SG
        raw_format = '<'
        for item in self._decoder.packet_info['decoding']:
            raw_format += item
        extra_data = structpp.unpack(raw_format, blob, asdict=True)

        if 'transform' in self._decoder.packet_info and self._decoder.packet_info['transform']:
            # Do some MDO processing or mapping to strings
            transform = self._decoder.packet_info['transform']
            for key in extra_data.keys():
                if key in transform:
                    extra_data[key] = self._process_transformations(extra_data[key], transform[key])

        return extra_data

    def _begin(self, stream_data):
        self._packet = []
        self._start = stream_data

    def _end(self, end):
        assert end.type == 'P-1'
        # There should never be an end of packet without a previous start of packet
        # But due to a firmware bug, this may happen. For now, just ignore the packet
        # TODO: Switch back to an assert when firmware issue fixed
        # assert self._start
        if not self._start:
            logger.warning('{0}Found END of packet without a START. Ignoring incorrect packet. End ID={1}'.format(
                self._stream.slug, end.streamer_local_id)
            )
            return None
        logger.debug('Process packet with {0} elements for {1}'.format(len(self._packet), self._stream.slug))
        if len(self._packet) == 0:
            return None

        # Create new Event record using timestamp and other info from the data stream
        event = StreamEventData(stream_slug=self._start.stream_slug,
                                streamer_local_id=self._start.streamer_local_id,
                                status=self._start.status,
                                device_timestamp=self._start.device_timestamp,
                                timestamp=self._start.timestamp)
        event.deduce_slugs_from_stream_id()

        # Decode all data and add as event.extra_data
        event.extra_data = self._unpack_data(end)

        return event

    def process_data_point(self, stream_data):
        if stream_data.type == 'P-0':
            # logger.debug('Begging packet at {}'.format(stream_data.streamer_local_id))
            self._begin(stream_data)
        elif stream_data.type == 'P-1':
            event = self._end(stream_data)
            return event
        else:
            self._packet.append(stream_data)
        return None
