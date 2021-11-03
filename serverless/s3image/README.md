
# S3Image worker Functions/API

This project will create the following functions

   * `resize`: Resize original image into thumbnail and tiny sizes

## Deployment

```
serverless deploy --stage dev
serverless deploy --stage prod
```

## Development

```
serverless invoke --stage dev -f resize -p event.json
serverless invoke --stage prod -f resize -p event.json
```

## logs

```
serverless logs --stage dev -f resize
serverless logs --stage prod -f resize
```

## Destroy

```
serverless remove --stage dev
serverless remove --stage prod
```