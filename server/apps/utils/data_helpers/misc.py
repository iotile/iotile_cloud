from iotile_cloud.utils.gid import *

from apps.utils.timezone_utils import convert_to_utc


def update_project_id(timeseries, stream):
    """Update timeseries.project_id by using stream information"""
    if stream.project_slug:
        timeseries.project_id = IOTileProjectSlug(stream.project_slug).get_id()


def update_device_and_block_id(timeseries, stream):
    """Update timeseries.device_id and timeseries.block_id by using stream information"""
    if stream.device_slug:
        if stream.device_slug[0] == 'b':
            timeseries.device_id = IOTileBlockSlug(stream.device_slug).get_id()
            timeseries.block_id = IOTileBlockSlug(stream.device_slug).get_block()
        else:
            timeseries.device_id = IOTileDeviceSlug(stream.device_slug).get_id()


def update_variable_id(timeseries, stream):
    """Update timeseries.variable_id by using stream information"""
    if stream.variable_slug:
        timeseries.variable_id = int(IOTileVariableSlug(stream.variable_slug).formatted_local_id(), 16)


def update_timestamp(timeseries, stream):
    """Update timeseries.timestamp by using stream information"""
    if stream.timestamp:
        timeseries.timestamp = convert_to_utc(stream.timestamp)


def update_every_id(timeseries, stream):
    """Update timeseries.project_id, timeseries.device_id, timeseries.block_id, and timeseries.variable_id by using stream information"""
    update_project_id(timeseries, stream)
    update_device_and_block_id(timeseries, stream)
    update_variable_id(timeseries, stream)


def update_project_and_variable_slug(stream, timeseries):
    """Update stream.project_slug and stream.variable_slug by using timeseries information"""
    if timeseries.project_id:
        iotile_project_slug = IOTileProjectSlug(timeseries.project_id)
        stream.project_slug = str(iotile_project_slug)
        if timeseries.variable_id:
            stream.variable_slug = str(IOTileVariableSlug(timeseries.variable_id, project=iotile_project_slug))


def update_device_slug(stream, timeseries):
    """Update stream.device_slug by using timeseries information"""
    if timeseries.device_id:
        if timeseries.block_id:
            stream.device_slug = str(IOTileBlockSlug(timeseries.device_id, block=timeseries.block_id))
        else:
            stream.device_slug = str(IOTileDeviceSlug(timeseries.device_id))


def update_every_slug(stream, timeseries):
    """Update stream.project_slug, stream.variable_slug, and stream.device_slug by using timeseries information"""
    update_project_and_variable_slug(stream, timeseries)
    update_device_slug(stream, timeseries)
