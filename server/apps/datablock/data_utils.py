from django.db.models import Count

from apps.stream.models import StreamId
from apps.utils.data_mask.mask_utils import get_data_mask_date_range
from apps.utils.data_helpers.manager import DataManager


class StreamDataCountHelper(object):
    """
    Creates a streams_totals dictionary with total data and event counts per stream in the form of:
    {
       'datas': <count>,
       'events': <count>,
       'has_streamid': True|False
    }

    It also keeps totals:
    - total_data_count
    - total_event_count

    And a data_mask if set
    """
    stream_totals = {}
    total_data_count = 0
    total_event_count = 0
    data_mask = None

    def __init__(self, block):
        self.stream_totals = {}
        self.total_data_count = 0
        self.total_event_count = 0
        self.data_mask = get_data_mask_date_range(block)

        distinct_data_stream_qs = DataManager.filter_qs('data', device_slug=block.slug)
        distinct_event_streams_qs = DataManager.filter_qs('event', device_slug=block.slug)

        if self.data_mask and self.data_mask['start']:
            distinct_data_stream_qs = distinct_data_stream_qs.filter(timestamp__gte=self.data_mask['start'])
            distinct_event_streams_qs = distinct_event_streams_qs.filter(timestamp__gte=self.data_mask['start'])
        if self.data_mask and self.data_mask['end']:
            distinct_data_stream_qs = distinct_data_stream_qs.filter(timestamp__lt=self.data_mask['end'])
            distinct_event_streams_qs = distinct_event_streams_qs.filter(timestamp__lt=self.data_mask['end'])

        distinct_data_streams = distinct_data_stream_qs.order_by('stream_slug').values('stream_slug').annotate(total=Count('id'))
        distinct_event_streams = distinct_event_streams_qs.order_by('stream_slug').values('stream_slug').annotate(total=Count('id'))

        for item in distinct_data_streams:
            self.total_data_count += item['total']

        for item in distinct_event_streams:
            self.total_event_count += item['total']

        for item in distinct_data_streams:
            if 'total' in item:
                item['data_count'] = item['total']
            if item['stream_slug'] in self.stream_totals:
                self.stream_totals[item['stream_slug']].update(item)
            else:
                self.stream_totals[item['stream_slug']] = item

        for item in distinct_event_streams:
            if 'total' in item:
                item['event_count'] = item['total']
            if item['stream_slug'] in self.stream_totals:
                self.stream_totals[item['stream_slug']].update(item)
            else:
                self.stream_totals[item['stream_slug']] = item

        for streamid in block.streamids.filter(enabled=True):
            if streamid.slug in self.stream_totals:
                self.stream_totals[streamid.slug]['has_streamid'] = True
