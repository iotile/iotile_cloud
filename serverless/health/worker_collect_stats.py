import datetime
import json
import logging
import os
import sys

from utils import handle_error, sqs_publish

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def publish_worker_collect_stats(event, context):
    """
    Publishes an SQS message for the worker to collect stats of the past day

    :param event: N/A
    :param context: N/A
    :return: message
    """
    try:
        dt_now = datetime.datetime.utcnow()
        sqs_publish({
            'module': 'apps.sqsworker.worker',
            'class': 'WorkerCollectStatsAction',
            'arguments': {
                'ts': dt_now.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'span': 'd'
            }
        })
        status = 200
        msg = 'Worker collect stats at {}'.format(dt_now)
    except Exception as e:
        status = 400
        msg = "Fail sending collect statistic task to worker. Exception: {}".format(str(e))
        handle_error(msg)

    response = {
        "statusCode": status,
        "body": json.dumps({
            "message": msg
        })
    }

    return response
