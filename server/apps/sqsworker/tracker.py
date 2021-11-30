import logging
import uuid

from django.core.cache import cache

from .common import ACTION_LIST

logger = logging.getLogger(__name__)

INFO_KEY_FORMAT = 'worker-info:{id}'
COUNT_KEY_FORMAT = 'worker-count:{id}'
ACTION_COUNT_KEY_FORMAT = 'worker-action-count:{name}'

_singleton_worker_uuid = None


class WorkerUUID(object):
    """
    This class manages the cache (Redis) that is used to keep
    track of worker stats.
    It ensures that a unique UUID is assigned for every active worker
    and it keeps track of associated counts for that worker

    This class is intended to be used as a SINGLETON so to get a reference to the
    one object per worker, use:
            worker_uuid = WorkerUUID.get_singleton()
    """
    id = None
    info_key = None
    count_key = None

    def __init__(self):
        self.id = uuid.uuid4()
        self.info_key = INFO_KEY_FORMAT.format(id=str(self.id))
        self.count_key = COUNT_KEY_FORMAT.format(id=str(self.id))

    def __str__(self):
        return str(self.id)

    def start(self, ts_now):
        if cache:
            logger.info('Worker started at {}'.format(ts_now))
            info = {
                'uuid': str(self.id),
                'start_dt': ts_now
            }
            cache.set(self.info_key, info, timeout=None)

            # We want count to represent since worker has started
            cache.set(self.count_key, 0, timeout=None)

            for action in ACTION_LIST:
                cache.set(self._action_key(action), 0, timeout=None)


    def increment_count(self):
        if cache:
            try:
                cache.incr(self.count_key)
            except Exception as e:
                logger.warning(str(e))

    def increment_action_count(self, name):
        if cache:
            try:
                cache.incr(self._action_key(name))
            except Exception as e:
                logger.warning(str(e))

    @property
    def count(self):
        if cache:
            try:
                return cache.get(self.count_key)
            except Exception:
                pass
        return 0

    @property
    def info(self):
        if cache:
            try:
                return cache.get(self.info_key)
            except Exception:
                pass
        return None

    def action_count(self, name):
        if cache:
            try:
                return cache.get(self._action_key(name))
            except Exception:
                pass
        return 0

    def _action_key(self, name):
        return ACTION_COUNT_KEY_FORMAT.format(name=name)

    @classmethod
    def get_worker_list(self):
        workers = []
        keys = None
        if cache:
            try:
                # Get all known workers from cache
                keys = cache.keys(INFO_KEY_FORMAT.format(id='*'))
            except Exception as e:
                # cache.keys is only available if using django-redis
                pass
            if keys:
                for k in keys:
                    info = cache.get(k)
                    if info:
                        parts = k.split(':')
                        if len(parts) == 2:
                            count = cache.get(COUNT_KEY_FORMAT.format(id=parts[1]))
                            if count != None:
                                info['count'] = count
                        workers.append(info)

        return workers

    @classmethod
    def cleanup(self, min_count=0):
        keys = None
        if cache:
            try:
                # Get all known workers from cache
                keys = cache.keys(COUNT_KEY_FORMAT.format(id='*'))
            except Exception as e:
                # cache.keys is only available if using django-redis
                pass

            if keys:
                for k in keys:
                    count = cache.get(k)
                    if count != None and count <= min_count:
                        cache.delete(k)
                        parts = k.split(':')
                        if len(parts) == 2:
                            info_key = INFO_KEY_FORMAT.format(id=parts[1])
                            if cache.get(info_key):
                                cache.delete(info_key)

    @classmethod
    def cleanup_id(self, worker_id):
        keys = None
        if cache:
            try:
                # Get worker from cache with given id
                count_key = COUNT_KEY_FORMAT.format(id=worker_id)
                if cache.get(count_key):
                    cache.delete(count_key)
                info_key = INFO_KEY_FORMAT.format(id=worker_id)
                if cache.get(info_key):
                    cache.delete(info_key)
            except Exception as e:
                # cache.keys is only available if using django-redis
                pass

    @classmethod
    def get_action_list(self):
        actions = []
        if cache:
            try:
                # Get all known workers from cache
                for action in ACTION_LIST:
                    actions.append({
                        'name': action,
                        'count': cache.get(ACTION_COUNT_KEY_FORMAT.format(name=action))
                    })
            except Exception as e:
                # cache.keys is only available if using django-redis
                pass
        return actions

    @classmethod
    def get_singleton(self):
        global _singleton_worker_uuid

        if not _singleton_worker_uuid:
            _singleton_worker_uuid = WorkerUUID()

        return _singleton_worker_uuid
