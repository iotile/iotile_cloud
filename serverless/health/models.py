import os
import sys

here = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(here, "./vendored"))

from pynamodb.attributes import BooleanAttribute, JSONAttribute, NumberAttribute, UnicodeAttribute, UTCDateTimeAttribute
from pynamodb.indexes import AllProjection, GlobalSecondaryIndex
from pynamodb.models import Model

DYNAMODB_WORKERLOG_TABLE_NAME = os.environ['dynamodb_workerlog_table_name']

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

    worker_uuid = UnicodeAttribute(hash_key=True)
    timestamp = UTCDateTimeAttribute(range_key=True)

    task = UnicodeAttribute()

    # Results
    status = UnicodeAttribute(default='executing')
    execution_time = NumberAttribute(null=True)
    arguments = JSONAttribute(null=True)

    # Secondary Global Index to search with item_uuid
    task_index = TaskIndex()
