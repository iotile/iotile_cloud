__author__ = 'dkarchmer'

import base64
import os
import io
import time
import hmac
import hashlib
import json
import boto3
import gzip
import logging
import tempfile
from io import BytesIO, StringIO

from django.conf import settings

# Get an instance of a logger
logger = logging.getLogger(__name__)

s3 = boto3.client('s3')
s3_resource = boto3.resource('s3')


def get_s3_url(bucket_name, key_name):
    # Generate the URL to get 'key-name' from 'bucket-name'
    url = s3.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': bucket_name,
            'Key': key_name
        }
    )

    return url

def get_s3_post_url(bucket_name, key_name, max_length, fields):

    conditions = [{key: fields[key]} for key in fields.keys()]
    conditions.append(['content-length-range', 10, max_length])

    # Generate the POST attributes
    post = s3.generate_presigned_post(
        Bucket=bucket_name,
        Key=key_name,
        Fields=fields,
        Conditions=conditions,
        ExpiresIn=60*60*6 # TODO: 4hr may be too long. Change to 10min after analytics workers is able to batch uploads
    )
    return post


# -----------------------------------
# Begin: New AWS Version 4 Signatures
# -----------------------------------
def sign(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def getSignatureKey(key, dateStamp, regionName, serviceName):
    kDate = sign(("AWS4" + key).encode("utf-8"), dateStamp)
    kRegion = sign(kDate, regionName)
    kService = sign(kRegion, serviceName)
    kSigning = sign(kService, "aws4_request")
    return kSigning


def sign_policy_document(policy_document, private_key):
    """ Sign and return the policy doucument for a simple upload.
    http://aws.amazon.com/articles/1434/#signyours3postform
    """
    policy = base64.b64encode(json.dumps(policy_document).encode('ascii'))
    signature = base64.b64encode(hmac.new(private_key.encode(), policy, hashlib.sha1).digest())
    result = {
        'policy': policy.decode(),
        'signature': signature.decode()
    }

    #print('sign Policy = ' + str(result))
    return result


# End: New AWS Version 4 Signatures
# ---------------------------------
def sign_headers(headers, private_key):
    """ Sign and return the headers for a chunked upload. """
    signature = base64.b64encode(hmac.new(private_key.encode(), headers.encode('ascii'), hashlib.sha1).digest())
    result = {
        'signature': signature.decode()
    }
    #print(str(result))
    return result


# Methods to write and read from S3
def upload_text_from_object(bucket, key, data):
    assert(data)
    io = None
    try:
        io = StringIO(data)
    except Exception as e:
        logger.error('Failed to create StreamIO with text data: {}'.format(e))
    if io:
        try:
            s3.put_object(Bucket=bucket, Key=key, Body=io.read())
            return True
        except Exception as e:
            logger.error('Failed to s3.put_object: {}'.format(e))
    return False


# Methods to write and read from S3
def upload_json_data_from_object(bucket, key, data):
    try:
        return upload_text_from_object(bucket, key, json.dumps(data))
    except Exception as e:
        logger.error('Failed to dump to json: {}'.format(e))
    return False


def download_text_as_object(bucket, key):
    obj = s3_resource.Object(bucket, key)
    text_data = obj.get()['Body'].read().decode('utf-8')
    return text_data


def download_json_data_as_object(bucket, key):
    json_data = download_text_as_object(bucket, key)
    return json.loads(json_data)


# Methods to write and read from S3
def upload_blob(bucket, key, blob, metadata=None):
    bucket_obj = s3_resource.Bucket(bucket)
    if bucket_obj:
        logger.info('Uploading blob to {0}:{1}'.format(bucket, key))
        try:
            if metadata:
                bucket_obj.upload_fileobj(blob, key, ExtraArgs={"Metadata": metadata})
            else:
                bucket_obj.upload_fileobj(blob, key)
        except Exception as e:
            logger.error('Failed to upload to s3: {}'.format(e))
            raise e
    else:
        logger.error('Failed to find bucket {0}'.format(bucket))


# blob is a file-like object to download the file into
def download_blob(bucket, key, blob):
    bucket_obj = s3_resource.Bucket(bucket)
    if bucket_obj:
        logger.info('Downloading blob {0} from bucket {1}'.format(key, bucket))
        try:
            bucket_obj.download_fileobj(key, blob)
        except Exception as e:
            logger.error('Failed to download from s3: {}'.format(e))
            raise e
    else:
        logger.error('Failed to find bucket {0}'.format(bucket))


def download_gzip_blob(bucket, key):
    """
    Download a .gz file from S3, and decompress

    :param bucket: S3 bucket
    :param key: S3 key
    :return: Decompressed file
    """
    bucket = s3_resource.Bucket(bucket)
    obj = bucket.Object(key)

    with io.BytesIO(obj.get()["Body"].read()) as compressed_file:

        compressed_file.seek(0)
        decompressed_file = gzip.GzipFile(fileobj=compressed_file).read()
        return decompressed_file


def get_s3_metadata(bucket, key):
    response = s3.head_object(Bucket=bucket, Key=key)
    return response['Metadata']


def download_file_from_s3(bucket, key):
    base = '-' + os.path.basename(key)
    fp = tempfile.NamedTemporaryFile(mode='w+b', prefix='s3-', suffix=base)
    download_blob(bucket, key, fp)
    return fp
