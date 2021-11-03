import os
import sys
import json
import datetime
import logging
from utils import sqs_publish, handle_error

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def publish_stream_data_healthcheck(event, context):
    """
    Publishes an SQS message for the worker to check Stream Data integrity

    :param event: N/A
    :param context: N/A
    :return: message
    """
    try:
        dt_now = datetime.datetime.utcnow()
        sqs_publish({
            'module': 'apps.staff.worker.healthcheck_stream_data',
            'class': 'HealthCheckStreamDataAction',
            'arguments': {
                'ts': dt_now.strftime('%Y-%m-%dT%H:%M:%SZ')
            }
        })
        status = 200
        msg = 'Stream Data Health Check at {}'.format(dt_now)
    except Exception as e:
        status = 400
        msg = "Fail sending health check stream data task to worker. Exception: {}".format(str(e))
        handle_error(msg)

    response = {
        "statusCode": status,
        "body": json.dumps({
            "message": msg
        })
    }

    return response