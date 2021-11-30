import datetime
import logging

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)
DYNAMODB_WORKERLOG_TABLE_NAME = getattr(settings, 'DYNAMODB_WORKERLOG_TABLE_NAME')
USE_DYNAMODB_WORKERLOG_DB = getattr(settings, 'USE_DYNAMODB_WORKERLOG_DB')
SERVER_TYPE = getattr(settings, 'SERVER_TYPE')


from pynamodb.attributes import BooleanAttribute, JSONAttribute, NumberAttribute, UnicodeAttribute, UTCDateTimeAttribute
from pynamodb.indexes import AllProjection, GlobalSecondaryIndex
from pynamodb.models import Model


class TaskIndex(GlobalSecondaryIndex):
    """
    This class represents a global secondary index
    """
    class Meta:
        # index_name is optional, but can be provided to override the default name
        index_name = 'task-index'
        read_capacity_units = 2
        write_capacity_units = 1
        # All attributes are projected
        projection = AllProjection()
        host = getattr(settings, 'DYNAMODB_URL')
    # This attribute is the hash key for the index
    task = UnicodeAttribute(hash_key=True)
    timestamp = UTCDateTimeAttribute(range_key=True)


class DynamoWorkerLogModel(Model):
    """
    A DynamoDB model caching some Device Data
    """
    class Meta:
        table_name = DYNAMODB_WORKERLOG_TABLE_NAME
        read_capacity_units = 2
        write_capacity_units = 2
        host = getattr(settings, 'DYNAMODB_URL')

    worker_uuid = UnicodeAttribute(hash_key=True)
    timestamp = UTCDateTimeAttribute(range_key=True)

    task = UnicodeAttribute()

    # Results
    status = UnicodeAttribute(default='executing')
    execution_time = NumberAttribute(null=True)
    arguments = JSONAttribute(null=True)

    # Secondary Global Index to search with item_uuid
    task_index = TaskIndex()


def create_worker_log(uuid, task, args):
    if USE_DYNAMODB_WORKERLOG_DB:
        now = timezone.now()
        logger.debug('Creating new DynamoWorkerLogModel for {0} at {1} : {2}'.format(uuid, now, task))
        try:
            obj = DynamoWorkerLogModel(worker_uuid=str(uuid), task=task, arguments=args, timestamp=now)
            obj.save()
            return obj
        except Exception as e:
            logger.warning(str(e))

    return None

def create_worker_log_table_if_needed():
    if not DynamoWorkerLogModel.exists():
        logger.info("Creating table for DynamoWorkerLogModel")
        DynamoWorkerLogModel.create_table(wait=True)
