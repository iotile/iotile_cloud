import json
import uuid

from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.streamtimeseries.models import StreamTimeSeriesEvent, StreamTimeSeriesValue

from .misc import update_every_id, update_every_slug, update_timestamp


class DataConverter:
    """
    Data and Event conversion helper
    """

    @staticmethod
    def data_to_tsvalue(data):
        """Convert a StreamData object into a StreamTimeSeriesValue object."""

        ts_value = StreamTimeSeriesValue(
            stream_slug=data.stream_slug,
            device_seqid=data.streamer_local_id,
            device_timestamp=data.device_timestamp,
            status=data.status,
            type=data.type,
            value=data.value,
            raw_value=data.int_value,
        )

        update_every_id(ts_value, data)
        update_timestamp(ts_value, data)

        return ts_value

    @staticmethod
    def tsvalue_to_data(ts_value):
        """Convert a StreamTimeSeriesValue object into a StreamData object."""

        data = StreamData(
            stream_slug=ts_value.stream_slug,
            device_timestamp=ts_value.device_timestamp,
            timestamp=ts_value.timestamp,
            streamer_local_id=ts_value.device_seqid,
            dirty_ts=False,
            status=ts_value.status,
            type=ts_value.type,
            value=ts_value.value,
            int_value=ts_value.raw_value,
        )

        update_every_slug(data, ts_value)

        return data

    @staticmethod
    def event_to_tsevent(event):
        """Convert a StreamEvent object into a StreamTimeSeriesEvent object."""

        ts_event = StreamTimeSeriesEvent(
            stream_slug=event.stream_slug,
            device_seqid=event.streamer_local_id,
            device_timestamp=event.device_timestamp,
            timestamp=event.timestamp,
            status=event.status,
            uuid=str(event.uuid),
            s3_key_path=event.s3_key_path,
            ext=event.ext,
            extra_data=event.extra_data,
            format_version=event.format_version,
        )

        update_every_id(ts_event, event)

        return ts_event

    @staticmethod
    def tsevent_to_event(ts_event):
        """Convert a StreamTimeSeriesEvent object into a StreamEventData object."""

        event = StreamEventData(
            stream_slug=ts_event.stream_slug,
            device_timestamp=ts_event.device_timestamp,
            timestamp=ts_event.timestamp,
            streamer_local_id=ts_event.device_seqid,
            dirty_ts=False,
            status=ts_event.status,
            uuid=uuid.UUID(ts_event.uuid),
            s3_key_path=ts_event.s3_key_path,
            ext=ts_event.ext,
            extra_data=ts_event.extra_data,
            format_version=ts_event.format_version,
        )

        update_every_slug(event, ts_event)

        return event

    @staticmethod
    def tsvalue_to_firehose(ts_value):
        """Convert a StreamTimeSeriesValue into a Firehose payload"""

        payload = {}
        fields = (
            'stream_slug',
            'project_id',
            'device_id',
            'block_id',
            'variable_id',
            'device_seqid',
            'device_timestamp',
            'timestamp',
            'status',
            'type',
            'value',
            'raw_value',
        )
        for key in fields:
            if getattr(ts_value, key) is not None:
                if key == 'timestamp':
                    payload[key] = ts_value.timestamp.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
                else:
                    payload[key] = getattr(ts_value, key)

        return payload

    @staticmethod
    def tsevent_to_firehose(ts_event):
        """Convert a StreamTimeSeriesValue into a Firehose payload"""

        payload = {}
        fields = (
            'stream_slug',
            'project_id',
            'device_id',
            'block_id',
            'variable_id',
            'device_seqid',
            'device_timestamp',
            'timestamp',
            'status',
            'uuid',
            's3_key_path',
            'ext',
            'extra_data',
            'format_version',
        )
        for key in fields:
            if getattr(ts_event, key) is not None:
                if key == 'timestamp':
                    payload[key] = ts_event.timestamp.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
                elif key == 'extra_data':
                    payload[key] = json.dumps(ts_event.extra_data)
                else:
                    payload[key] = getattr(ts_event, key)

        return payload
