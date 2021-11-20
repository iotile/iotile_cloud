#!/bin/bash
aws ecr get-login-password --profile iotile_cloud --region us-east-1 | docker login -u AWS --password-stdin xxxxxxxxxxxxxx.dkr.ecr.us-east-1.amazonaws.com
docker build -t iotile-cloud-server .
docker tag iotile-cloud-server:latest xxxxxxxxxxxxxx.dkr.ecr.us-east-1.amazonaws.com/iotile-cloud-server:latest
docker push xxxxxxxxxxxxxx.dkr.ecr.us-east-1.amazonaws.com/iotile-cloud-server:latest
