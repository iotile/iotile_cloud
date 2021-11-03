from django.conf import settings
from django.core.cache import cache

from apps.utils.aws.sqs import get_queue_stats

from .worker import WORKER_LAST_PIN_DT
from .dynamodb import DynamoWorkerLogModel, USE_DYNAMODB_WORKERLOG_DB
from .common import ACTION_LIST
from .tracker import WorkerUUID
from .pid import ActionPID

WORKER_QUEUE_NAME = getattr(settings, 'SQS_WORKER_QUEUE_NAME')

class WorkerStats(object):
    sqs = {}
    last_ping_dt = None
    tasks = {}
    workers = []
    active = []

    def __init__(self):
        """
        Get all stats at initialization time
        """

        # SQS Stats
        self.sqs = get_queue_stats(WORKER_QUEUE_NAME)

        # Last heartbeat time
        if cache:
            self.last_ping_dt = cache.get(WORKER_LAST_PIN_DT)

        self.workers = WorkerUUID.get_worker_list()
        self.active = ActionPID.all()

    def get_action_stats(self):
        if USE_DYNAMODB_WORKERLOG_DB:
            self.actions = WorkerUUID.get_action_list()
            for a in self.actions:
                try:
                    a['total'] = DynamoWorkerLogModel.count(hash_key=a['name'], consistent_read=False, index_name='task-index')
                except Exception as e:
                    a['total'] = str(e)
