
# Health Checks

Set of functions to check different aspects of the overall system health

* *dev* for local development
* *stage* for https://cloud.corp.archsys.io
* *prod* for https://iotile.cloud

Use `--stage <type>` to deploy, invoke, get logs or destroy

## Functions

Next are the current functions created:

```
functions:
  workerCheck: health-prod-workerCheck
  deviceCheck: health-prod-deviceCheck
  streamDataCheck: health-prod-streamDataCheck
  cleanupWorkerLogs: health-prod-cleanupWorkerLogs
  workerCollectStats: health-prod-workerCollectStats
  collectDbStats: health-prod-collectDbStats
  cacheOEE: health-prod-cacheOEE
```

## Deployment

```
serverless deploy --stage dev
serverless deploy --stage stage
serverless deploy --stage prod
```

## Execute for Testing

```
serverless invoke -f workerCheck --stage dev
serverless invoke -f workerCheck --stage stage
serverless invoke -f workerCheck --stage prod

serverless invoke -f streamDataCheck --stage stage
serverless invoke -f workerCollectStats --stage stage
serverless invoke -f cleanupWorkerLogs --stage stage
```

## logs

```
serverless logs -f workerCheck --stage dev
serverless logs -f workerCheck --stage stage
serverless logs -f workerCheck --stage prod
```

## Destroy

```
serverless remove --stage dev
serverless remove --stage stage
serverless remove --stage prod
```

## To install requirements, run :
pip install -t vendored/ -r requirements.txt