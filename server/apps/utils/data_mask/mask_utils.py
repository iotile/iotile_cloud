import logging

from django.utils import timezone

from apps.streamnote.models import StreamNote
from apps.utils.data_helpers.manager import DataManager
from apps.utils.iotile.variable import SYSTEM_VID

logger = logging.getLogger(__name__)


def _log_data_mask_as_note(obj, start, end, user):
    if start or end:
        msg = 'Data mask set ('
        if start:
            msg += ' start: {}'.format(start)
        if end:
            msg += ' end: {}'.format(end)
        msg += ' )'
    else:
        msg = 'Data mask cleared'

    StreamNote.objects.create(target_slug=obj.slug,
                              timestamp=timezone.now(),
                              note=msg,
                              created_by=user)


def set_data_mask(obj, start, end, data_exceptions, event_excetions, user):
    """
    Find existing Event or create a new one and use event.extra_data to set
    the start and end of the mask.

    Create a StreamNote to log change

    :param obj: Device or DataBlock Object
    :param start: Datetime as UTC str
    :param end: Datetime as UTC str
    :param data_exceptions: Currently not use. Set to []
    :param event_excetions: Currently not use. Set to []
    :param user: User that is makring change
    :return: Modified or new StreamEventData object
    """

    payload = {
        'start': start,
        'end': end,
        'events': event_excetions,
        'data': data_exceptions
    }

    stream_slug = obj.get_stream_slug_for(SYSTEM_VID['DEVICE_DATA_MASK'])

    event = DataManager.filter_qs('event', stream_slug=stream_slug).last()
    if not event:
        event = DataManager.build(
            'event',
            timestamp=timezone.now(),
            stream_slug=str(stream_slug),
            status='cln',
            extras={
                'extra_data': payload,
            },
        )
        event.deduce_slugs_from_stream_id()
    else:
        event.timestamp = timezone.now()
        event.extra_data = payload

    DataManager.save('event', event)
    logger.info('Created/Updated new Device Mask Event: {}'.format(stream_slug))

    _log_data_mask_as_note(obj=obj, start=start, end=end, user=user)

    return event


def clear_data_mask(obj, user, notify=True):
    """
    Find existing Event for device mask and if it exit, delete

    Create a StreamNote to log change

    :param obj: Device or DataBlock Object
    :param user: User that is makring change
    :return: Nothing
    """

    stream_slug = obj.get_stream_slug_for(SYSTEM_VID['DEVICE_DATA_MASK'])

    qs = DataManager.filter_qs('event', stream_slug=stream_slug)
    if qs.exists():
        qs.delete()
        logger.info('Deleted Device Mask Event: {}'.format(stream_slug))
        if notify:
            _log_data_mask_as_note(obj=obj, start=None, end=None, user=user)


def get_data_mask_event(obj):
    """
    :param obj: Device or DataBlock Object
    :return: StreamEventData if a mask has been set
    """
    mask_stream_slug = obj.get_stream_slug_for(SYSTEM_VID['DEVICE_DATA_MASK'])
    if mask_stream_slug:
        return DataManager.filter_qs('event', stream_slug=mask_stream_slug).last()
    return None


def get_data_mask_date_range(obj):
    """
    :param obj: Device or DataBlock Object
    :return: A Dict with {'start': '<datetime_str>', 'end': '<datetime_str>'}. None if not set
    """
    event = get_data_mask_event(obj)
    if event:
        assert('start' in event.extra_data)
        assert('end' in event.extra_data)
        return event.extra_data
    return None


def get_data_mask_date_range_for_slug(mask_stream_slug):
    """
    :param mask_stream_slug: Stream Slug
    :return: StreamEventData if a mask has been set
    """
    event = DataManager.filter_qs('event', stream_slug=str(mask_stream_slug)).last()
    if event:
        assert('start' in event.extra_data)
        assert('end' in event.extra_data)
        return event.extra_data
    return None
