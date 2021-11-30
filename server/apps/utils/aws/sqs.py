import json
import logging

import boto3

from django.conf import settings

from .common import AWS_REGION

logger = logging.getLogger(__name__)

if settings.SQS_URL:
    print(f'Using {settings.SQS_URL=}')
    sqs = boto3.resource('sqs',
                         region_name=AWS_REGION,
                         aws_access_key_id=None,
                         aws_secret_access_key=None,
                         endpoint_url=settings.SQS_URL)
    sqs_client = boto3.client('sqs',
                              region_name=AWS_REGION,
                              aws_access_key_id=None,
                              aws_secret_access_key=None,
                              endpoint_url=settings.SQS_URL)
else:
    sqs = boto3.resource('sqs', region_name=AWS_REGION)
    sqs_client = boto3.client('sqs', region_name=AWS_REGION)

def get_queue_by_name(queue_name):
    """
    Get SQS queue given a queue name
    :param queue_name: name of queue. eg. iotile-worker-prod
    :return: Boto3 SQS queue object
    """
    try:
        sqs_queue = sqs.get_queue_by_name(QueueName=queue_name)
        return sqs_queue
    except Exception as e:
        logger.error("Fail to get SQS queue {}. Error: {}".format(queue_name, str(e)))
        raise e


def get_queue_url(queue_name):
    """
    Get URL to access SQS queue
    :param queue_name: name of queue. eg. iotile-worker-prod
    :return: URL
    """
    try:
        response = sqs_client.get_queue_url(QueueName=queue_name)
        return response['QueueUrl']
    except Exception as e:
        logger.error("Fail to get SQS queue {}. Error: {}".format(queue_name, str(e)))
        raise e


def get_queue_stats(queue_name):
    """
    Get basic stats on the given Queue
    :param queue_name: name of queue. eg. iotile-worker-prod
    :return: Dict with results
    """
    response = sqs_client.get_queue_attributes(
        QueueUrl=get_queue_url(queue_name),
        AttributeNames=[
            'ApproximateNumberOfMessages',
            'ApproximateNumberOfMessagesNotVisible',
            'ApproximateNumberOfMessagesDelayed',
        ]
    )
    result = response['Attributes']
    return result


def get_sqs_messages(queue, count):
    """
    Get a number of SQS messages, if available
    :param queue: Boto3 SQS Queue object
    :param max: Maximum number of messages to get. Usually 1 to 10
    :return: list of messages, up to count
    """
    return queue.receive_messages(MaxNumberOfMessages=count)


def post_sqs_message(queue, payload, delay=0):
    """
    Send a new SQS message for backend processing
    :param queue: Boto3 SQS Queue object
    :param payload: Json Serializable Python object
    :param delay: Delay in second. How much time to delay before message becomes active
    :return: Nothing
    """
    try:
        return queue.send_message(MessageBody=json.dumps(payload), DelaySeconds=delay)
    except Exception as e:
        logger.error("Fail to post SQS message: {}".format(str(e)))
        raise e


def change_sqs_message_visibility(message, time_out):
    """Change visibility timeout of message from queue
    This function should be called when handing an exception that is
    unrelated to the message itself, and therefore, we want the message
    to be requeued as fast as possible
    :param queue_name: for the SQS in question
    :param message: Active message we are processing and want to change
    :param time_out: Time in seconds we are changing the visibility
    :return: Nothing
    """
    try:
        message.change_visibility(
            VisibilityTimeout=123
        )
    except Exception as err:
        logger.error("Fail to change SQS change_visibility: {}".format(str(err)))
        raise err


class SqsPublisher(object):
    """
    Used to publish message to sqs queue
    """
    queue = None

    def __init__(self, queue_name):
        self.queue = get_queue_by_name(queue_name)

    def publish(self, payload, delay=0):
        """
        Publish SQS message
        :param payload: dict to use to create json object
        :param delay: delay in seconds. Max 15min
        """
        response = post_sqs_message(self.queue, payload=payload, delay=delay)
        logger.info('Message sent - Message ID: {0}'.format(response.get('MessageId')))
