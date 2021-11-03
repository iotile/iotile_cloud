#!/bin/bash

cd /var/app
export PYTHONPATH=/var/app;$PYTHONPATH

python manage.py migrate --no-input
python manage.py migrate --no-input --database=streamdata

python manage.py init-basic-data
python manage.py set-product-data
python manage.py set-ot-data
python manage.py set-pt-data
python manage.py set-var-type-data
python manage.py set-sg-data
python manage.py add-test-data

python manage.py create_worker_log_db_table

python manage.py search_index --rebuild -f

#/usr/local/bin/gunicorn config.wsgi:application -w 2 -b :8000
/usr/local/bin/gunicorn --log-level info --log-file=- --workers 4 --name arch_gunicorn -b 0.0.0.0:8000 --reload config.wsgi:application