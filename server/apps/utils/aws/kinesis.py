__author__ = 'dkarchmer'

import datetime
import json
import logging
import pprint

import boto3

from django.conf import settings

from .common import AWS_REGION

# Get an instance of a logger
logger = logging.getLogger(__name__)

FIREHOSE_STREAM_NAME = getattr(settings, 'FIREHOSE_STREAM_NAME')

firehose_client = boto3.client('firehose', region_name=AWS_REGION)


def _write_stream(stream, firehose_client):
    try:
        response = firehose_client.put_record(
            DeliveryStreamName=FIREHOSE_STREAM_NAME,
            Record={
                'Data': json.dumps(stream)
            }
        )
        logging.info(response)
    except Exception:
        logging.exception('Problem pushing to firehose')


def _write_stream_batch(records, firehose_client):
    try:
        response = firehose_client.put_record_batch(
            DeliveryStreamName=FIREHOSE_STREAM_NAME,
            Records=records
        )
        if 'FailedPutCount' in response and response['FailedPutCount']:
            logger.error('Firehose: {0} upload failures detected'.format(response['FailedPutCount']))

    except Exception as e:
        logging.debug(e)
        logging.exception('Firehose: upload failures detected. {}'.format(str(e)[0:50]))


def datetime_handler(x):
    if isinstance(x, datetime.datetime):
        return x.isoformat()
    raise TypeError("Unknown type")


def send_to_firehose(data, batch_num):

    batch_payload = []
    count = 1
    for item in data:
        # print(str(stream_payload))
        batch_item = {
            'Data': json.dumps(item, default=datetime_handler)
        }
        batch_payload.append(batch_item)
        count += 1
        if count == batch_num:
            logger.info('Uploading {0} records'.format(batch_num))
            _write_stream_batch(batch_payload, firehose_client)
            batch_payload = []
            count = 1

    if len(batch_payload):
        logger.info('Uploading final {0} records'.format(len(batch_payload)))
        _write_stream_batch(batch_payload, firehose_client)
