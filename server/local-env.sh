#!/bin/bash
# type: source local-env.sh
export DJANGO_SETTINGS_MODULE=config.settings.development
export DJANGO_SERVER_MODE=Test
export DJANGO_SECRET_KEY=dummy
export AWS_PROFILE=iotile_cloud
export DJANGO_ENV_FILE=.local.env
export PRODUCTION=0