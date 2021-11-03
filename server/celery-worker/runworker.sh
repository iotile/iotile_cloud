#!/bin/bash

# wait for RabbitMQ server to start
sleep 10

cd /var/app/

su -m myuser -c "celery worker -A celery-worker -l info"