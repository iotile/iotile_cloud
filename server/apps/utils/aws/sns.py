import json
import logging

import boto3

from django.conf import settings

from .common import AWS_REGION

# Get an instance of a logger
logger = logging.getLogger(__name__)

SNS_STREAM_WORKER = getattr(settings, 'SNS_STREAM_WORKER')
SNS_STAFF_NOTIFICATION = getattr(settings, 'SNS_STAFF_NOTIFICATION')
SNS_ARCH_SLACK_NOTIFICATION = getattr(settings, 'SNS_ARCH_SLACK_NOTIFICATION')

sns_client = boto3.client('sns', AWS_REGION)


def sns_lambda_message(topic, message):
    '''
    Use SNS to send a task to a background Lambda Function
    '''
    try:
        logger.info('Publishing SNS: {0}'.format(topic))
        if getattr(settings, 'PRODUCTION'):
            response = sns_client.publish(
                TargetArn=topic,
                Message=json.dumps({'default': json.dumps(message)}),
                MessageStructure='json'
            )
        else:
            logger.info("Not in production, skip publishing")
            return True
    except Exception as ex:
        logging.error('Error with SNS message: %s' % str(ex))

    return False


def _sns_text_based_notification(topic, message):
    """
    Generic method to publish an SNS notification
    
    :param topic: SNS ARN address for SNS topic
    :param message: String to be published
    :return: True if successful
    """
    try:
        logger.info('Publishing to: {0} -- {1}'.format(topic, message))
        response = sns_client.publish(
            TargetArn=topic,
            Message=message,
            MessageStructure='string'
        )
        logger.info(str(response))
        return True
    except Exception as ex:
        logging.error('Error with SNS message: {}'.format(str(ex)))

    return False


def sns_staff_notification(message):
    '''
    Use SNS to publish an SNS to Staff
    '''
    if settings.ENABLE_STAFF_SNS_NOTIFICATIONS:
        return _sns_text_based_notification(SNS_STAFF_NOTIFICATION, message)
    else:
        logger.warning(message)
        return True


def sns_arc_slack_notification(message):
    '''
    Use SNS to publish message to Arch #iotile-cloud channel
    '''

    return _sns_text_based_notification(SNS_ARCH_SLACK_NOTIFICATION, message)
