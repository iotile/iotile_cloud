import logging
from django.core.cache import cache
from django.conf import settings

from .models import StreamFilter
from .serializers import StreamFilterSerializer

logger = logging.getLogger(__name__)


_stream_filter_format = lambda elements: '--'.join(['f', ] + elements[1:])
_project_filter_format = lambda elements: '--'.join(['f', elements[1], '', elements[3]])


def _get_filter_cache_key(slug):
    return ':'.join(['filter', slug])


def _get_cached_filter(key):
    if cache:
        key = _get_filter_cache_key(key)
        result = cache.get(key)
        if result:
            logger.debug('StreamFilter: cache(HIT)={0}'.format(key))
            return result
    return None


def _cache_filter(key, obj):
    serializer = StreamFilterSerializer(obj)
    data = serializer.data
    if cache:
        key = _get_filter_cache_key(key)
        logger.info('StreamFilter: cache(SET)={0}'.format(key))
        cache.set(key, data, timeout=3000)
    return data


def _cached_serialized_filter_for_slug_elements(elements):
    assert(len(elements) == 4)

    # 1.- Check if results are already on the cache for a stream
    filter_stream_slug = _stream_filter_format(elements)
    result = _get_cached_filter(filter_stream_slug)
    if result:
        return result

    # 2.- Check cache again, but now for a project filter
    filter_project_slug = _project_filter_format(elements)
    result = _get_cached_filter(filter_project_slug)
    if result:
        return result

    # ======================== Not found in Cache. Read from Database

    # 3.- First, see if there is a filter defined for the full stream slug
    obj = None
    try:
        obj = StreamFilter.objects.get(slug=filter_stream_slug)
        return _cache_filter(filter_stream_slug, obj)
    except StreamFilter.DoesNotExist:
        logger.info('StreamFilter not found for Stream {}'.format(filter_stream_slug))

    # 4.- If not, check for a project wide filter
    if not obj:
        try:
            obj = StreamFilter.objects.get(slug=filter_project_slug)
            return _cache_filter(filter_project_slug, obj)
        except StreamFilter.DoesNotExist:
            logger.info('StreamFilter not found for Project {}'.format(filter_project_slug))

    if cache:
        logger.info('StreamFilter: cache(SET-EMPTY)={0}'.format(filter_stream_slug))
        cache.set(_get_filter_cache_key(filter_stream_slug), {'empty': True})
    return {'empty': True}


def cached_serialized_filter_for_slug(slug):
    elements = slug.split('--')
    return _cached_serialized_filter_for_slug_elements(elements)


def cached_serialized_filter_for_gsid(gsid):
    elements = gsid.split('--')
    return _cached_serialized_filter_for_slug_elements(elements)


def clear_serialized_filter_for_slug(slug):
    key = _get_filter_cache_key(slug)
    logger.info('Attempting to delete cache entries for {0} ({1})'.format(key, slug))
    if cache:
        if cache.get(key):
            logger.info('Cache: Deleting{}'.format(key))
            cache.delete(key)
        state_key_patern = get_current_state_cache_pattern(slug)
        logger.info('Cache: Deleting {}'.format(state_key_patern))
        cache.delete_pattern(state_key_patern)


def _get_current_state_cache_key(slug):
    return ':'.join(['current-state', slug])


def get_current_cached_filter_state_for_slug(slug):
    key = _get_current_state_cache_key(slug)
    if cache:
        return cache.get(key)
    # TODO: We may need to add a proper Redshift model to store on master database, instead of just cache
    return None


def set_current_cached_filter_state_for_slug(slug, state):
    key = _get_current_state_cache_key(slug)
    if cache:
        # print('New StreamFilterState for {0}: {1}'.format(slug, state))
        # Never expires
        cache.set(key=key, value=state, timeout=None)


def get_current_state_cache_pattern(slug):
    # Given a filter slug, which could represent a project filter slug
    # return all current_state instances in the cache
    assert cache
    elements = slug.split('--')
    assert(len(elements) == 4)
    if elements[2] == '':
        patern = '--'.join(['s', elements[1], '*', elements[3]])
    else:
        patern = '--'.join(['s', ] + elements[1:])

    return _get_current_state_cache_key(patern)


