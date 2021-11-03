import uuid
import logging

from django.core.cache import cache
from django.utils import timezone

from apps.utils.timezone_utils import str_utc

logger = logging.getLogger(__name__)

ACTION_PID_KEY_FORMAT = 'pid:{id}'
TIMEOUT = 60*60*24


class ActionPID(object):
    """
    This class manages the cache (Redis) that is used to keep
    track of shceduled SQS messages.
    It is used on top of SQS to allow users to get a process id on a background task
    """
    id = None
    type = None
    key = None

    def __init__(self, id, type=None):
        parts = id.split(':')
        if len(parts) > 1:
            self.id = parts[1]
        else:
            self.id = id
        if type:
            self.type = type
        self.key = ACTION_PID_KEY_FORMAT.format(id=self.id)

    def __str__(self):
        return 'pid:{}'.format(self.id)

    def _commit(self, info, timeout=TIMEOUT):
        if cache:
            logger.info('ActionPID: {}={}'.format(self.key, self.info()))
            cache.set(self.key, info, timeout=timeout)

    def start(self):
        ts_now = timezone.now()
        logger.info('{} crated at {}'.format(self.key, ts_now))
        info = {
            'id': self.id,
            'type': self.type if self.type else 'Unk',
            'dt': str_utc(ts_now)
        }
        self._commit(info)

    def info(self):
        if cache:
            try:
                return cache.get(self.key)
            except Exception:
                pass
        return None

    @classmethod
    def all(self):
        results = []
        keys = None
        if cache:
            try:
                # Get all known device states from cache
                keys = cache.keys(ACTION_PID_KEY_FORMAT.format(id='*'))
            except Exception:
                # cache.keys is only available if using django-redis
                pass

            if keys:
                for k in keys:
                    results.append(cache.get(k))

        return results

    @classmethod
    def delete_all(self):
        keys = None
        if cache:
            try:
                # Get all known device states from cache
                keys = cache.keys(ACTION_PID_KEY_FORMAT.format(id='*'))
            except Exception:
                # cache.keys is only available if using django-redis
                pass

            if keys:
                for k in keys:
                    obj = cache.get(k)
                    if obj != None:
                        cache.delete(k)

    @classmethod
    def delete(self, id):
        if cache:
            try:
                # Get device state from cache with given id
                key = ACTION_PID_KEY_FORMAT.format(id=id)
                if cache.get(key):
                    logger.info('ActionPID: Deleting {}'.format(key))
                    cache.delete(key)
            except Exception:
                # cache.keys is only available if using django-redis
                pass
