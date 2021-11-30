import logging

from django import template

from apps.stream.helpers import StreamDataDisplayHelper, StreamDataQueryHelper

register = template.Library()
logger = logging.getLogger(__name__)


@register.simple_tag
def divide(a, b):
    if b > 1:
        return '{0:.4f}'.format(a / b)
    return a


@register.simple_tag
def check_trigger(stream, value):
    return stream.evaluate(value)


@register.simple_tag
def display_value(stream, value):
    helper = StreamDataDisplayHelper(stream)
    return helper.format_value(helper.output_value(value))


@register.simple_tag
def display_value_with_units(stream, value):
    helper = StreamDataDisplayHelper(stream)
    return helper.format_value(helper.output_value(value), True)


@register.filter
def last_value(stream):
    helper = StreamDataQueryHelper(stream)
    last_item_list = helper.get_data_for_filter({"lastn": 1})
    if last_item_list:
        helper = StreamDataDisplayHelper(stream)
        return helper.format_value(helper.output_value(last_item_list[0].int_value))
    return 0.0


@register.filter
def last_int_value(stream):
    helper = StreamDataQueryHelper(stream)
    last_item_list = helper.get_data_for_filter({"lastn": 1})
    if last_item_list:
        return last_item_list[0].int_value
    return 0


@register.simple_tag
def modified_last_value(stream, with_units):
    helper = StreamDataQueryHelper(stream)
    last_item_list = helper.get_data_for_filter({"lastn": 1})
    if last_item_list:
        '''
        value = stream.float_value(last_item_list[0].int_value)

        if stream.marker_stream_id != '0000':
            stream_ids = [ stream.marker_stream_id,]
            sorted_items = StreamDataTable.get_stream_data(stream_ids, 1)
            if len(sorted_items):
                reset_value = sorted_items[0].value
                logger.info('Adjusting {0} by {1} ==> {2}'.format(value, reset_value, value+reset_value))
                value += reset_value
        '''

        helper = StreamDataDisplayHelper(stream)
        return helper.format_value(helper.output_value(last_item_list[0].value), with_units)
    return ''


@register.filter
def last_record(stream):
    print('Last of {}'.format(stream))
    try:
        helper = StreamDataQueryHelper(stream)
        sorted_items = helper.get_data_for_filter({"lastn": 1})
        if sorted_items:
            return sorted_items[0]
        return None
    except Exception:
        return None


@register.filter
def record_count(stream):
    try:
        return stream.get_data_count()
    except Exception:
        return 0


@register.filter
def get_stream_data(stream):
    helper = StreamDataQueryHelper(stream)
    return helper.get_data_for_filter({"lastn": 1000})

