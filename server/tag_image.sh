#!/bin/bash
aws ecr get-login-password --profile iotile_cloud --region us-east-1 | docker login -u AWS --password-stdin 868687213780.dkr.ecr.us-east-1.amazonaws.com
docker build -t iotile-cloud-server .
docker tag iotile-cloud-server:latest 868687213780.dkr.ecr.us-east-1.amazonaws.com/iotile-cloud-server:latest
docker push 868687213780.dkr.ecr.us-east-1.amazonaws.com/iotile-cloud-server:latest
