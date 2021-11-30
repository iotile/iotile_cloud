import logging
from functools import wraps

from django.core.cache import caches
from django.views.decorators.cache import cache_page

from rest_framework import status, viewsets
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class APICachedRetrieveViewSet(viewsets.ModelViewSet):
    _cache = caches['default']

    def _key(self, request):
        return ':'.join(['api', request.get_full_path()])

    def retrieve(self, request, *args, **kwargs):
        key = self._key(request)
        if self._cache:
            data = self._cache.get(key)
            if data:
                return Response(data)

        response = super(APICachedRetrieveViewSet, self).retrieve(request, *args, **kwargs)
        if self._cache and response.status_code == status.HTTP_200_OK:
            logger.info('Cache SET {}'.format(key))
            self._cache.set(key, response.data, 300)

        return response


def cached_serializer(cache):
    def true_decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            instance = args[1]
            cache_key = ':'.join(['api', instance.slug])
            logger.debug('%s cache_key: %s' % (cache, cache_key))
            try:
                data = caches[cache].get(cache_key)
                if data is not None:
                    return data
            except:
                pass

            data = f(*args, **kwargs)
            try:
                caches[cache].set(cache_key, data)
            except:
                pass
            return data
        return wrapper
    return true_decorator


def cache_on_auth(timeout, key_prefix):
    """
    Decorator on top of the default cache_page, but ensures only authenticated pages are cached

    :param timeout: How long to keep on cache
    :return: decorator
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_authenticated:
                # key = get_cache_key(request, key_prefix=key_prefix)
                # print(key)
                return cache_page(timeout, key_prefix=key_prefix)(view_func)(request, *args, **kwargs)
            else:
                return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator