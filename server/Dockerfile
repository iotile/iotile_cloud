# Use exact version used by Codeship and AWS
FROM python:3.8

ENV C_FORCE_ROOT 1

# create unprivileged user
RUN adduser --disabled-password --gecos '' myuser

# Install PostgreSQL dependencies
RUN apt-get update && \
    apt-get install -y postgresql-client libpq-dev supervisor


# Step 1: Install any Python packages
# ----------------------------------------

ENV PYTHONUNBUFFERED 1
RUN mkdir /var/app
WORKDIR  /var/app
COPY requirements /var/app/requirements
ADD requirements.txt /var/app/requirements.txt
RUN pip install -U pip
RUN pip install -r requirements/docker.txt
RUN pip install gunicorn


# Step 2: Copy Django Code
# ----------------------------------------

COPY apps /var/app/apps
COPY config /var/app/config
COPY templates /var/app/templates
COPY manage.py /var/app/manage.py
COPY runserver.sh /var/app/runserver.sh
COPY runtest.sh /var/app/runtest.sh
COPY locale /var/app/locale
COPY supervisord.conf /var/app/supervisord.conf
RUN mkdir /var/app/logs
