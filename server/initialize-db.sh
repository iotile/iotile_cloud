#!/bin/bash

set -e

python manage.py migrate
python manage.py migrate --database=streamdata

python manage.py init-basic-data
python manage.py set-ot-data
python manage.py set-pt-data
python manage.py set-product-data
python manage.py set-var-type-data
python manage.py set-sg-data
python manage.py add-test-data

python manage.py create_worker_log_db_table
# python manage.py create_filter_log_dynamodb_table

python manage.py search_index --rebuild -f

# Display all dynamodb tables. There should be 4
aws dynamodb list-tables --endpoint-url http://dynamodb@127.0.0.1:8001/dynamodb --output json