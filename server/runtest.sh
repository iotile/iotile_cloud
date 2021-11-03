#!/bin/bash

#cd /var/app
#export PYTHONPATH=/var/app;$PYTHONPATH

sleep 30
python ./manage.py migrate --no-input
python ./manage.py migrate --no-input --database=streamdata
python ./manage.py search_index --rebuild -f
py.test --cov-config .coveragerc --cov=apps .
