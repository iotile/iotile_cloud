import os
import sys
import json
import datetime
import logging
from utils import sqs_publish, handle_error

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def publish_worker_healthcheck(event, context):
    """
    Publishes an SQS message for the worker to do a self-check

    :param event: N/A
    :param context: N/A
    :return: message
    """
    try:
        msg = 'Worker Health Check at {}'.format(datetime.datetime.utcnow())
        sqs_publish({
            'module': 'apps.sqsworker.worker',
            'class': 'WorkerHealthCheckAction',
            'arguments': {
                'message': msg
            }
        })
        status = 200
    except Exception as e:
        status = 400
        msg = "Fail sending health check task to worker. Exception: {}".format(str(e))
        handle_error(msg)

    response = {
        "statusCode": status,
        "body": json.dumps({
            "message": msg
        })
    }

    return response