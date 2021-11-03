import configparser
import pprint

config = configparser.ConfigParser()
config.read('../.ini')


def register_sqs_worker_tasks(ecs_client, family_name):
    # Create a task definition
    response = ecs_client.register_task_definition(
        containerDefinitions=[
            {
                "name": "worker-sqs",
                "image": "xxxxxxxxxxxxxxxxxxxxxxx.dkr.ecr.us-east-1.amazonaws.com/iotile-cloud-server:latest",
                "essential": True,
                "memory": 1000,
                "cpu": 256,
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": "iotile_cloud-worker-sqs",
                        "awslogs-region": "us-east-1",
                        "awslogs-stream-prefix": "iotile_cloud"
                    }
                },
                "environment": [
                    {
                        "name": "DJANGO_SETTINGS_MODULE",
                        "value": "config.settings.ecs.worker"
                    },
                    {
                        "name": "DJANGO_ENV_FILE",
                        "value": ".production.env"
                    },
                    {
                        "name": "DOCKER",
                        "value": "True"
                    },
                    {
                        "name": "PRODUCTION",
                        "value": "True"
                    },
                    {
                        "name": "DEBUG",
                        "value": "False"
                    },
                    {
                        "name": "SERVER_TYPE",
                        "value": "prod"
                    },
                    {
                        "name": "USE_WORKER",
                        "value": "True"
                    },
                    {
                        "name": "SENTRY_ENABLED",
                        "value": "True"
                    },
                    {
                        "name": "RDS_HOSTNAME",
                        "value": "xxxxxxxxxxxxxxxxxxxxx.us-east-1.rds.amazonaws.com"
                    },
                    {
                        "name": "RDS_PORT",
                        "value": "5432"
                    },
                    {
                        "name": "RDS_DB_NAME",
                        "value": "iotiledb1"
                    },
                    {
                        "name": "RDS_USERNAME",
                        "value": "ebroot"
                    },
                    {
                        "name": "REDIS_HOSTNAME",
                        "value": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxx.cache.amazonaws.com"
                    },
                    {
                        "name": "REDIS_PORT",
                        "value": "6379"
                    },
                    {
                        "name": "CACHE_URL",
                        "value": "rediscache://xxxxxxxxxxxxxxxxxxxxxx.cache.amazonaws.com:6379:1?client_class=django_redis.client.DefaultClient"
                    },
                    {
                        "name": "REDSHIFT_HOSTNAME",
                        "value": "xxxxxxxxxxxxxxxxxxxxa.us-east-1.redshift.amazonaws.com"
                    },
                    {
                        "name": "REDSHIFT_PORT",
                        "value": "5439"
                    },
                    {
                        "name": "REDSHIFT_DB_NAME",
                        "value": "iotiledb2"
                    },
                    {
                        "name": "AWS_ELASTICSEARCH_HOST",
                        "value": "vpc-xxxxxxxxxxxx.us-east-1.es.amazonaws.com"
                    },
                    {
                        "name": "DOMAIN_NAME",
                        "value": "iotile.cloud"
                    },
                    {
                        "name": "DOMAIN_BASE_URL",
                        "value": "https://iotile.cloud"
                    },
                    {
                        "name": "WEBAPP_BASE_URL",
                        "value": "https://app.iotile.cloud"
                    },
                    {
                        "name": "TWILIO_FROM_NUMBER",
                        "value": "+14432724468"
                    },
                ],
                "command": ["/usr/bin/supervisord", "-c", "/var/app/supervisord.conf"]
            }
        ],
        family=family_name
    )
    pprint.pprint(response)
