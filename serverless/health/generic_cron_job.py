import os
import sys
import json
import datetime
import logging
from utils import sqs_publish, handle_error

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

TASK_MODULE = os.environ['task_module']
TASK_CLASS = os.environ['task_class']
TASK_SPAN = os.environ['task_span']


def schedule_job(event, context):
    """
    Publishes an SQS message for the worker to collect stats of the past day

    :param event: N/A
    :param context: N/A
    :return: message
    """
    try:
        dt_now = datetime.datetime.utcnow()
        sqs_publish({
            'module': TASK_MODULE,
            'class': TASK_CLASS,
            'arguments': {
                'ts': dt_now.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'span': TASK_SPAN
            }
        })
        status = 200
        msg = 'Worker collect stats at {}'.format(dt_now)
    except Exception as e:
        status = 400
        msg = "Fail sending generic task to worker. Exception: {}".format(str(e))
        handle_error(msg)

    response = {
        "statusCode": status,
        "body": json.dumps({
            "message": msg
        })
    }

    return response
