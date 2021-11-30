import json
import logging
import uuid

from django.conf import settings

logger = logging.getLogger(__name__)
DYNAMODB_FILTER_LOG_TABLE_NAME = getattr(settings, 'DYNAMODB_FILTER_LOG_TABLE_NAME')
SERVER_TYPE = getattr(settings, 'SERVER_TYPE')

from pynamodb.attributes import BooleanAttribute, JSONAttribute, NumberAttribute, UnicodeAttribute, UTCDateTimeAttribute
from pynamodb.indexes import AllProjection, GlobalSecondaryIndex
from pynamodb.models import Model

from .models import StreamFilter
from .serializers import StreamFilterActionSerializer


class TargetIndex(GlobalSecondaryIndex):
    class Meta:
        index_name = 'target_index'
        read_capacity_units = 2
        write_capacity_units = 1
        projection = AllProjection()
        host = getattr(settings, 'DYNAMODB_URL')

    target_slug = UnicodeAttribute(hash_key=True)
    timestamp = UTCDateTimeAttribute(range_key=True)


class DynamoFilterLogModel(Model):
    class Meta:
        table_name = DYNAMODB_FILTER_LOG_TABLE_NAME
        read_capacity_units = 2
        write_capacity_units = 2
        host = getattr(settings, 'DYNAMODB_URL')

    uuid = UnicodeAttribute(hash_key=True)

    # stream slug (or device slug as a larger log level)
    target_slug = UnicodeAttribute()

    # Timestamp of the Filter
    timestamp = UTCDateTimeAttribute()

    # state change
    src = UnicodeAttribute(default='')
    dst = UnicodeAttribute()

    # triggers, json list
    triggers = JSONAttribute()

    target_index = TargetIndex()


def create_filter_log_table_if_needed():
    if not DynamoFilterLogModel.exists():
        logger.info("Creating table for DynamoFilterLogModel")
        DynamoFilterLogModel.create_table(wait=True)


def create_filter_log(target_slug, timestamp, src, dst, triggers):
    if not getattr(settings, 'USE_DYNAMODB_FILTERLOG_DB'):
        return None
    if not src:
        src = '*'
    attributes = {
        "target_slug": target_slug,
        "timestamp": timestamp,
        "src": src,
        "dst": dst,
        "triggers": triggers
    }
    filter_id = uuid.uuid4()
    try:
        filter_log = DynamoFilterLogModel(uuid=str(filter_id), **attributes)
        filter_log.save()
        return filter_id
    except Exception as e:
        logging.error('Error creating filter log: %s' % str(e))
    return None
