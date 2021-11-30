# In production set the environment variable like this:
#    DJANGO_SETTINGS_MODULE=config.settings.production
import logging.config
import socket

from ..base import *  # NOQA

# For security and performance reasons, DEBUG is turned off
DEBUG = False
TEMPLATES[0]['OPTIONS'].update({'debug': False})

TIME_ZONE = 'UTC'

print('**********************************')
print('**********************************')
print('INFO: ECS SQS Worker Settings')
print('INFO: Debug = {0}'.format(DEBUG))
print('**********************************')
print('**********************************')

# No need for HTTP security, as this is a worker with no open ports
local_ip = str(socket.gethostbyname(socket.gethostname()))
print('IP={}'.format(local_ip))
ALLOWED_HOSTS = ['*', ]

# Setup CloudFront
AWS_S3_URL_PROTOCOL = 'https'
# Enable one AWS_S3_CUSTOM_DOMAIN to use cloudfront
AWS_S3_CUSTOM_DOMAIN = 'cdn.iotile.cloud'
STATIC_URL = AWS_S3_URL_PROTOCOL + '://' + AWS_S3_CUSTOM_DOMAIN + '/static/'

print('AWS_S3_CUSTOM_DOMAIN = {0}, STATIC_URL={1}'.format(AWS_S3_CUSTOM_DOMAIN, STATIC_URL))

# Email Config
# ------------
EMAIL_BACKEND = 'django_ses.SESBackend'
print('EMAIL_BACKEND = {0}'.format(EMAIL_BACKEND))

# Kinesis Firehose:
# -----------------
USE_FIREHOSE = True

# SQS Info
# --------
USE_DYNAMODB_WORKERLOG_DB = True
USE_DYNAMODB_FILTERLOG_DB = True

# SNS notifications are enabled for production worker
ENABLE_STAFF_SNS_NOTIFICATIONS = True
