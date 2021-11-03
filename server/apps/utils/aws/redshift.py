import pytz
import datetime
from django.conf import settings


def get_time_difference_server_utc():
    server_tz = pytz.timezone(getattr(settings, 'TIME_ZONE'))
    server_now = datetime.datetime.now(server_tz)
    hour_diff = server_now.utcoffset().total_seconds()/60/60
    return hour_diff


def get_ts_from_redshift(ts):
    """
    :param ts: a datetime object from Redshift, example streamdata.timestamp
    :return: datetime object in UTC, use this value to write to redshift
    """
    if ts.tzinfo:
        ts = ts.replace(tzinfo=pytz.utc)
    else:
        ts = pytz.utc.localize(ts)
    return ts
