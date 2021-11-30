import json
import logging
import os
import pprint

import boto3

s3 = boto3.client('s3')
logger = logging.getLogger()
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


def deleteS3Obj(event, context):
    if event and 'Records' in event and len(event['Records']) and 'Sns' in event['Records'][0] and 'Message' in event['Records'][0]['Sns']:
        msg = event['Records'][0]['Sns']['Message']

    if not msg:
        logger.error('No Event Data')
        resp = {
            "statusCode": 400,
            "body": 'No event data'
        }
        return resp

    payload = json.loads(msg)

    results = []

    for item in payload:
        if 'bucket' in item and 'key' in item:
            try:
                logger.info("Deleting object from s3, bucket: {}, key: {}".format(item['bucket'], item['key']))
                response = s3.delete_object(Bucket=item['bucket'], Key=item['key'])
                result_item = {
                    "item": item,
                    "response": response
                }
                results.append(result_item)
            except Exception as e:
                msg = "Fail to delete object. Error {}".format(str(e))
                logger.error(msg)
                sns_notification(msg)
                return {
                    "statusCode": 400,
                    "body": msg
                }
        else:
            return {
                "statusCode": 400,
                "body": "Missing fields in payload. Payload recieved: {}".format(payload)
            }

    print(str(results))
    return {
        "statusCode": 200,
        "results": results,
    }