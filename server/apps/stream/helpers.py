import logging

from apps.utils.data_helpers.manager import DataManager
from apps.utils.data_mask.mask_utils import get_data_mask_date_range_for_slug
from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.mdo.helpers import MdoHelper
from apps.utils.timezone_utils import str_to_dt_utc

from .models import StreamId

# Get an instance of a logger
logger = logging.getLogger(__name__)


class StreamDataQueryHelper(object):
    _data_stream = None
    _data_stream_slug = None
    _stream = None

    def __init__(self, stream):
        self._stream = stream
        if self._stream.derived_stream:
            self._stream_data = self._stream.derived_stream
        else:
            self._stream_data = stream
        self._data_stream_slug = self._stream_data.slug

    def _get_basic_data_qs(self):
        stream_id = self._data_stream_slug
        return DataManager.filter_qs('data', stream_slug=stream_id)

    def _get_basic_event_qs(self):
        stream_id = self._data_stream_slug
        return DataManager.filter_qs('event', stream_slug=stream_id)

    def _get_data_qs(self, qs, num=None, ascending=True):
        sorted_items = qs.order_by('-timestamp')[:num]
        if ascending:
            sorted_items = sorted_items[::-1]
        return sorted_items

    def _sort_qs(self, qs):
        return qs.order_by('timestamp')

    def _get_start_and_end_dates(self, filter):
        """
        Resolve conflicts between any given filter and the device data mask. If

        :param filter: Dict with any existing filter. A filter may come from an API parameter (self.request.GET).
        :return: Dictionary with 'start' and 'end' set as datetimes if set, and accounting for mask
        """
        start = None
        end = None

        if 'start' in filter:
            start = str_to_dt_utc(filter['start'])
        if 'end' in filter:
            end = str_to_dt_utc(filter['end'])

        mask_stream_slug = self._stream.get_stream_slug_for(SYSTEM_VID['DEVICE_DATA_MASK'])
        mask = get_data_mask_date_range_for_slug(mask_stream_slug)
        if mask and mask['start']:
            mask_start = str_to_dt_utc(mask['start'])
            if start:
                if mask_start > start:
                    start = mask_start
            else:
                start = mask_start

        if mask and mask['end']:
            mask_end = str_to_dt_utc(mask['end'])
            if end:
                if mask_end < end:
                    end = mask_end
            else:
                end = mask_end

        return start, end

    def _get_data_for_period_qs(self, start, end, qs):
        if start:
            qs = qs.filter(timestamp__gte=start)
        if end:
            qs = qs.filter(timestamp__lt=end)

        return qs

    def get_data_for_filter(self, filter_dict, ascending=True, event=False):

        # 1. Get basic query set for stream
        if event:
            qs = self._get_basic_event_qs()
        else:
            qs = self._get_basic_data_qs()

        # 2. Filter by date if required
        start, end = self._get_start_and_end_dates(filter_dict)
        if start or end:
            qs = self._get_data_for_period_qs(qs=qs, start=start, end=end)

        # 3. Sort data
        qs = self._sort_qs(qs)

        # 4.- Filter by lastN if required
        if 'lastn' in filter_dict:
            try:
                lastn = int(filter_dict['lastn'])
                # Limit lastn from 1 to 10,000
                if lastn < 1:
                    lastn = 1
                elif lastn > 10000:
                    lastn = 100000

                qs = self._get_data_qs(qs, num=lastn, ascending=ascending)
            except Exception:
                # If wrong integer, just ignore
                pass

        return qs


class StreamDataDisplayHelper(object):
    _stream = None
    _derived_stream = None

    def __init__(self, stream):
        self._stream = stream
        self._derived_stream = self._stream.derived_stream

    def input_value(self, value):
        if (not isinstance(value, int) and not isinstance(value, float)):
            return None
        if value == None:
            return 0.0
        ret_value = 0.0

        # We should be storing a consistent unit on StreamData but until we do, we need to
        # compute both the input and output MDOs
        if self._stream.input_unit:
            input_mdo = MdoHelper(self._stream.input_unit.m, self._stream.input_unit.d, self._stream.input_unit.o)
            value = input_mdo.compute(value)
        else:
            value = float(value)

        if self._stream.mdo_type == 'V':
            var = self._stream.variable
            var_mdo = MdoHelper(var.multiplication_factor, var.division_factor, var.offset)
            ret_value += var_mdo.compute(value)

        elif self._stream.mdo_type == 'S':
            m = 1
            d = 1
            if self._stream.multiplication_factor != None:
                m = self._stream.multiplication_factor
            if self._stream.division_factor != None:
                d = self._stream.division_factor

            stream_mdo = MdoHelper(m, d, self._stream.offset)
            ret_value += stream_mdo.compute(value)

        return ret_value

    def _base_output_value(self, stream, value):

        if stream.derived_stream:
            value = self._base_output_value(stream=stream.derived_stream, value=value)

        if stream.output_unit:
            # New Scheme
            output_mdo = MdoHelper(stream.output_unit.m, stream.output_unit.d, stream.output_unit.o)
            ret_value = output_mdo.compute(value)
        else:
            ret_value = value

        return ret_value

    def output_value(self, value):
        if (not isinstance(value, int) and not isinstance(value, float)):
            return None
        if value == None:
            return 0.0

        ret_value = self._base_output_value(stream=self._stream, value=value)

        if self._derived_stream:
            if self._stream.derived_selection != '':
                out_unit = self._stream.derived_variable.output_unit
                if out_unit:
                    if self._stream.derived_selection in out_unit.derived_units:
                        derived_mdo = MdoHelper(
                            m=out_unit.derived_units[self._stream.derived_selection]['m'],
                            d=out_unit.derived_units[self._stream.derived_selection]['d']
                        )
                        ret_value = derived_mdo.compute(ret_value)
                        return ret_value

        return ret_value

    def format_value(self, value, with_units=False):
        if value == None:
            return 'ERR'
        var = self._stream.variable
        if var:
            prec = var.decimal_places
        else:
            prec = 2
        format_str = '{0:0.{prec}f}'
        display_value = format_str.format(value, prec=prec)

        if with_units:
            if self._stream.output_unit:
                units = self._stream.output_unit.unit_short
            else:
                if var.output_unit:
                    units = var.output_unit.unit_short
                else:
                    units = var.units
            display_value += ' {0}'.format(units)
        return display_value
