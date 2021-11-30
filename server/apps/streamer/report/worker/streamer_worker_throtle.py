import logging

from django.core.cache import cache

from apps.sqsworker.exceptions import WorkerActionHardError

logger = logging.getLogger(__name__)


class StreamerWorkerThrotle(object):
    streamer_slug = None
    key = None
    action = None

    def __init__(self, action, streamer_slug):
        self.action = action
        self.streamer_slug = streamer_slug
        self.key = ':'.join(['streamer-processing-attempt', self.streamer_slug])

    def _get_action_name(self):
        return self.action.get_name()

    def begin_process(self):
        assert(cache)
        attempts = cache.get(self.key, 0)
        if attempts == 0:
            # Expires in 10hrs so the process should finish before that
            cache.set(self.key, 1, 36000)
            return True
        else:
            logger.warning('[{0}] New attempt to process a streamer that is being processed. key={1}, count={2}'.format(
                self._get_action_name(), self.streamer_slug, str(cache.get(self.key))))
            # For every failed attempt, just increment
            try:
                cache.incr(self.key, 1)
            except Exception as e:
                logger.warning('Unable to increase cache, key={0}, error={1}'.format(self.key, str(e)))
                raise WorkerActionHardError(str(e))

            # Notify Admins if we have tried more than 5 times
            if attempts // 20:
                if (attempts % 20) == 0:
                    self.action.notify_admins('{}'.format(self._get_action_name()),
                                              'Has seen {0} attempts to run a parallel worker task. Args:\n{1}'.format(
                                              attempts, str(self.action.sqs_arguments)))
            if attempts >= 100:
                # Give up after 100
                self.action.notify_admins('{}'.format(self._get_action_name()),
                                          '100 attempts. Giving up. Args:\n{0}'.format(str(self.action.sqs_arguments)))
                self.end_process()

            return False

    def end_process(self):
        logger.info('[{0}] Clearing cache({1})={2}'.format(self._get_action_name(), self.key, cache.get(self.key)))
        try:
            cache.delete(self.key)
        except Exception as e:
            logger.warning('Unable to delete cache, key={0}, error={1}'.format(self.key, str(e)))
            raise WorkerActionHardError(str(e))


