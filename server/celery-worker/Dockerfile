# Use exact version used by Codeship and AWS
FROM python:3.8

ENV C_FORCE_ROOT 1

# create unprivileged user
RUN adduser --disabled-password --gecos '' myuser


# Step 1: Install any Python packages
# ----------------------------------------

ENV PYTHONUNBUFFERED 1
RUN mkdir /var/app
WORKDIR  /var/app
COPY requirements /var/app/requirements
ADD requirements.txt /var/app/requirements.txt
RUN pip install -U pip
RUN pip install -r requirements/docker.txt

# Step 2: Copy Django Code
# ----------------------------------------
COPY apps /var/app/apps
COPY celery-worker /var/app/celery-worker
COPY config /var/app/config
COPY locale /var/app/locale
COPY manage.py /var/app/manage.py

ADD . /var/app
