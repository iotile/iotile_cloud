#!/bin/bash
# Script to build the webapp with Gulp and to collect the statics

# 1.- Build docker container used to build
docker build -t iotile/webapp webapp

# 2.- Delete all previous files. Need to delete from docker because files get created as root
docker run --rm -v ${PWD}/webapp:/var/app/webapp -t iotile/webapp rm -rf /var/app/webapp/node_modules
docker run --rm -v ${PWD}/staticfiles:/var/app/staticfiles -t iotile/webapp rm -rf /var/app/staticfiles/admin
docker run --rm -v ${PWD}/staticfiles:/var/app/staticfiles -t iotile/webapp rm -rf /var/app/staticfiles/dist
docker run --rm -v ${PWD}/staticfiles:/var/app/staticfiles -t iotile/webapp rm -rf /var/app/staticfiles/debug_toolbar
docker run --rm -v ${PWD}/staticfiles:/var/app/staticfiles -t iotile/webapp rm -rf /var/app/staticfiles/drf-yasg
docker run --rm -v ${PWD}/staticfiles:/var/app/staticfiles -t iotile/webapp rm -rf /var/app/staticfiles/rest_framework
docker run --rm -v ${PWD}/server:/var/app/server -t iotile/webapp rm -rf /var/app/server/templates/dist
docker run --rm -v ${PWD}/server:/var/app/server -t iotile/webapp mkdir /var/app/server/templates/dist /var/app/server/templates/dist/webapp

# 3.- Build WebApp
docker run --rm -v ${PWD}/webapp:/var/app/webapp -v ${PWD}/server:/var/app/server -v ${PWD}/staticfiles:/var/app/staticfiles -t iotile/webapp npm install
docker run --rm -v ${PWD}/webapp:/var/app/webapp -v ${PWD}/server:/var/app/server -v ${PWD}/staticfiles:/var/app/staticfiles -t iotile/webapp gulp
