import logging
import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from .common import AWS_REGION

logger = logging.getLogger(__name__)


