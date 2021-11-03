import logging

from django.core.cache import cache

from apps.sqsworker.exceptions import WorkerActionHardError, WorkerActionSoftError
from apps.utils.data_helpers.manager import DataManager
from apps.utils.iotile.variable import SYSTEM_VID

logger = logging.getLogger(__name__)

MAX_ATTEMPT = 5


class DelayChecker(object):
    device = None
    project = None
    key = None
    action = None
    attempts = 0

    def __init__(self, action, device, project, start_id, end_id):
        self.action = action
        self.device = device
        self.project = project
        self.start_id = start_id
        self.end_id = end_id
        self.attempts = 0
        self.key = ':'.join(['delay-process', self.device.slug, str(self.start_id), str(self.end_id)])

    def _get_action_name(self):
        return self.action.get_name()

    def ready_to_process(self):
        """
        Check 2 conditions:
        - Streamers of the device has all the data in redshift if we can retrieve the data point of the streamer's last_id
        - User report of block [start_id, end_id] has been processed if user_streamer.last_id > start_id
        start_id: id of a system report, start of block
        end_id: id of a system report, end of block
        :return: True if data are ready to be processed
        """
        for streamer in self.device.streamers.all():
            if streamer.last_id:
                if not streamer.triggers_block_completeness and streamer.last_id < self.start_id:
                    logger.info("User streamer is not in sync with system streamer")
                    # Instead of taking all streamers that are not system streamer
                    # We may need to precise streamer index if we don't want to wait for all streamers to be up to date with the block
                    return False
                # Device can be moved to another project but haven't sent any data yet. Streamer can still be up to date with data of the old project
                if not DataManager.filter_qs('data', device_slug=self.device.slug,
                                             project_slug__in=[self.device.project.slug, self.project.slug],
                                             streamer_local_id__gte=streamer.last_id,
                                             variable_slug__endswith=SYSTEM_VID['COMPLETE_REPORT'],
                                             extras={'int_value': streamer.index}).exists():
                    logger.info("Checking data point of streamer {} not found. Last id {}".format(streamer.slug, streamer.last_id))
                    return False
        return True

    def continue_delay(self):
        """
        Continue delay if number of attempts < MAX_ATTEMPT
        :return: True if we should delay the process to retry later
        """
        assert(cache)
        self.attempts = cache.get(self.key, 0)
        if self.attempts == 0:
            # Expires in 10hrs so the process should finish before that
            cache.set(self.key, 1, 36000)
            self.attempts = 1
            return True
        elif self.attempts < MAX_ATTEMPT:
            logger.warning('[{0}] New attempt to process a data range from id {1} to {2} but streamer is not ready. Key={3}, count={4}'.format(
                self._get_action_name(), self.start_id, self.end_id, self.key, str(cache.get(self.key))))
            try:
                cache.incr(self.key, 1)
            except Exception as e:
                logger.warning('Unable to increase cache, key={0}, error={1}'.format(self.key, str(e)))
                raise WorkerActionHardError(str(e))
            self.attempts += 1
            return True
        else:
            # Give up, notify admin
            raise WorkerActionHardError('{}'.format(self._get_action_name()), '{} attempts. Giving up. Args:\n{}'.format(MAX_ATTEMPT, str(self.action.sqs_arguments)))

    def delete_count(self):
        logger.info('[{0}] Clearing cache({1})={2}'.format(self._get_action_name(), self.key, cache.get(self.key)))
        try:
            if cache.get(self.key):
                cache.delete(self.key)
        except Exception as e:
            logger.warning('Unable to delete cache, key={0}, error={1}'.format(self.key, str(e)))
            raise WorkerActionHardError(str(e))
