import datetime
import logging

import pytz
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date

logger = logging.getLogger(__name__)

Y2K = datetime.datetime(2000, 1, 1)


def formated_timedelta(total_seconds):
    """
    Format time delta as H:M:S\

    :param total_seconds: from timedelta.totalseconds
    :return: formatted string
    """
    if isinstance(total_seconds, str):
        parts = total_seconds.split(':')
        if len(parts) > 1:
            # Assume already formatted
            return total_seconds
        try:
            # Assume an integer as a string
            total_seconds = int(total_seconds)
        except ValueError:
            # Don't know what this is, just return as is
            return total_seconds
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    return f'{hours}:{minutes}:{seconds}'


# dt is a datetime object
def convert_to_utc(dt):
    if dt.tzinfo:
        dt_utc = dt.astimezone(pytz.timezone('UTC'))
    else:
        # set the datetime object in django current_time_zone
        if timezone.get_current_timezone():
            dt_current_tz = pytz.timezone(timezone.get_current_timezone_name()).localize(dt)
            dt_utc = dt_current_tz.astimezone(pytz.timezone('UTC'))
        else:
            # If current timezone is not set, use utc
            dt_utc = pytz.timezone('UTC').localize(dt)
    return dt_utc


def str_to_dt_utc(str):
    #  should always use this to obtain an timezone-aware datetime object
    dt = parse_datetime(str)
    if not dt:
        # Try to convert a date to datetime
        d = parse_date(str)
        if d:
            dt = parse_datetime('{}T00:00:00Z'.format(d))
    return dt

def force_to_utc(dt_str):
    """
    Given a string, force it to a UTC DateTime
    If the string represents a timezone, return None
    
    :param dt_str: string representing date 
    :return: DateTime (UTC). None if not UTC
    """
    if dt_str[-6] in ['-', '+']:
        return str_to_dt_utc(dt_str)
    if not dt_str.endswith('Z'):
        # Assume this dt is UTC even if not specified
        dt_str = dt_str + 'Z'
    utc_dt = str_to_dt_utc(dt_str)

    return utc_dt


def formatted_ts(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def display_formatted_ts(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def str_utc(dt):
    dt_utc = convert_to_utc(dt)
    if dt_utc:
        return formatted_ts(dt_utc)
    else:
        logger.error("Fail to convert to datetime utc string")
        return None


def nb_seconds_since_2000(dt):
    dt_utc = convert_to_utc(dt)
    y2k_utc = convert_to_utc(Y2K)
    if dt_utc:
        return (dt_utc - y2k_utc).total_seconds()
    else:
        logger.error("Fail to convert to datetime utc string")
        return None
