import os
import sys
import json
import datetime
import logging
from utils import handle_error

here = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(here, "./vendored"))
import pytz
from models import DynamoWorkerLogModel

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

RETENTON_POLICY = 30

def cleanup_worker_logs(event, context):
    """
    Clean up worker logs everyday at 12am. Keep logs dated less than a month
    :param event: NA
    :param context: NA
    :return:
    """
    try:
        now = datetime.datetime.utcnow()
        items = DynamoWorkerLogModel.scan(timestamp__le=now - datetime.timedelta(days=RETENTON_POLICY), status__eq="done")
        for item in items:
            item.delete()
        status = 200
        msg = 'Clean up worker logs at {}'.format(now)
    except Exception as e:
        status = 400
        msg = "Fail cleaning up worker logs. Exception: {}".format(str(e))
        handle_error(msg)

    response = {
        "statusCode": status,
        "body": json.dumps({
            "message": msg
        })
    }

    return response