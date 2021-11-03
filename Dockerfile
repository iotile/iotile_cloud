FROM python:3.8-slim-buster
# ==========================================================
# Docker Image used for running build/release commands
# Includes Python 3.7+
# Usage:
#    docker build -t builder .
#    docker run --rm -v ${PWD}/webapp:/usr/src/app -t builder
#    docker run --rm -v ${PWD}/webapp:/usr/src/app --entrypoint npm -t builder install
#    docker run --rm -v ${PWD}/webapp:/usr/src/app -t builder templates
# ==========================================================


ENV C_FORCE_ROOT 1

# create unprivileged user
RUN adduser --disabled-password --gecos '' myuser

# Install PostgreSQL dependencies
RUN apt-get update && \
    apt-get install -y \
       curl \
       g++ \
       gcc \
       make \
       wget \
       postgresql-client \
       libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/

RUN mkdir -p /var/app

RUN mkdir -p /var/app
WORKDIR /var/app

# Install Python dependencies
ADD requirements.txt /var/app/requirements.txt
ADD server/requirements/base.txt /var/app/server/requirements/base.txt
RUN pip install -r requirements.txt
ADD server/requirements/docker.txt /var/app/server/requirements/docker.txt
RUN pip install -r server/requirements/docker.txt

# ENTRYPOINT ["invoke"]