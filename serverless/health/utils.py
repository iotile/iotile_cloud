import json
import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

SQS_QUEUE_NAME = os.environ['sqs_queue_name']
sqs_client = boto3.client('sqs')

SNS_TOPIC = os.environ['sns_topic']
sns_client = boto3.client('sns')


def sns_notification(message):
    try:
        logger.info('Publishing SNS: {0}'.format(SNS_TOPIC))
        response = sns_client.publish(
            TargetArn=SNS_TOPIC,
            Message=message,
            MessageStructure='json'
        )
        return True
    except Exception as ex:
        logging.error('Error with SNS message: %s' % str(ex))
    return False


def handle_error(msg):
    logger.error(msg)
    sns_notification(msg)


def sqs_publish(obj):

    # Get URL for SQS queue
    response = sqs_client.get_queue_url(QueueName=SQS_QUEUE_NAME)
    if response:
        url = response['QueueUrl']
        logger.debug(str(json.dumps(obj)))
        response = sqs_client.send_message(
            QueueUrl=url,
            MessageBody=json.dumps(obj),
            DelaySeconds=0,
        )
        logger.debug(str(response))


