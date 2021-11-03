
# Health Checks

Set of functions to check different aspects of the overall system health

* *dev* for local development
* *stage* for https://cloud.corp.archsys.io
* *prod* for https://iotile.cloud

Use `--stage <type>` to deploy, invoke, get logs or destroy

## Functions

### workerHealth

Wakes up every x time and sends an SQS message to the worker to self-test

## Deployment

```
serverless deploy --stage dev
serverless deploy --stage stage
serverless deploy --stage prod
```

## Execute for Testing

```
serverless invoke -f delete_s3 --stage dev
serverless invoke -f delete_s3 --stage stage
serverless invoke -f delete_s3 --stage prod
```

## logs

```
serverless logs -f delete_s3 --stage dev
serverless logs -f delete_s3 --stage stage
serverless logs -f delete_s3 --stage prod
```

## Destroy

```
serverless remove --stage dev
serverless remove --stage stage
serverless remove --stage prod
```

## To install requirements, run :
pip install -t vendored/ -r requirements.txt