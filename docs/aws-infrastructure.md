# AWS Infrastructure

IOTile Cloud is heavily dependent on many AWS services. This document attempts to describe all of them. Note that this document does not explain much about why we need what we need. It simply describes what the infrastructure is.

## Python Invoke

All deployment tasks are automated via [python invoke](http://www.pyinvoke.org/) tasks, defined on [../tasks.py](tasks.py)

## Front End Server (ElasticBeanstalk)

The front end, Django Server is implemented using **AWS Elastic Beanstalk**, with several custom configurations. Configurations are stored under [../server/.ebextensions/](.ebextensions) and include:

- **00:httpd_django.config**: Modifying `/etc/httpd/conf.d/ssl_rewrite.conf` to ensure any HTTP request is forwarded to HTTPS.
- **01_pandas.config**: Installs addiional Linux OS packages required for Pandas to run.
- **02_main.config**: Main elastic beanstalk confirguration with required production environment variables (`RDS_HOSTNAME`, `REDIS_HOSTNAME`, `REDSHIFT_HOSTNAME`, etc.) as well as the commands that have to be run before the server can be started (e.g. `django-admin.py migrate`).
- **03_ec2.config**: Contains the required autoscaling configuration including the EC2 InstanceType to use when scaling up, and the expectad size (min and max of instances). 
- **04-loadbalancer.config**: Contains the required Load Balancer configuration, including the `SSLCertificateId`.
- **05_notifications.config**: Configures the SNS notifications for us to be notified on stack issues (alarms).
- **06_logs.config**: sets up the logging configuration.

ElasticBeanstalk will take care of managing:

- A **AWS Loadbalancer**
- all required **AWS EC2** machines
- **AWS Auto Scaling**
- Required **AWS Security Groups**

Note that we do NOT allow ElasticBeanstalk to manage our RDS database. Instead, this database is created and managed outside elastick beanstalk. This is important to ensure the database does not get deleted if we kill the eb environment.

In theory, we should be able to bring down the whole environment/application and recreate it without destroying any of the databases.

The elastic beanstalk environment was first created with `inv create` and all changes are deployed with `inv deploy` (see requirement for killing workers below before running this command). `deploy` deploys all static files, elastic beanstalk setup and the ECS workers, so when doing localized server changes, we just `cd server; eb deploy`.

## Backend Workers (ECS)

All asynchronous tasks are executed using a set of workers implemented as Docker containers running on **AWS ECS**.

All ECS tasks are defined under [ecs/tasks.py](../ecs/tasks.py). The infrastructure requires

- **AWS EC2** instances needed by the **ECS Cluster** to run jobs on.
- **AWS Elastic Container Registry (ECR)**
  - This was created manually on the console
- The whole cluster is created with `create_ecs` which itself runs `inv create_ec2_instances` to create any required EC2 instances.
- Changes are ultimately deployed by `inv deply-worker` which calls `inv build_docker` to build docker image and deploy to ECR and then `inv update_ecs` which creates a new **ECS Task**.

Workers are the only part of the infrastructure that require manual tasks to deploy. This because we currently have no way to deploy changes without affecting a running task.

Day to day, changes are then deployed by:

1. Calling `inv shutdown-ecs-workers` which queues a **kill** message to each running worker. Once the message is processed by a given worker, the worker sends a notification and enters an infinite loop to prevent any more tasks to be processed. 
1. Once we get a notification (currently via Sentry) for every worker (as of March 2019, 6 workers are used), it is safe to run `inv deploy-worker` or `inv deploy` if a full deployment is done. This command relies on.

While we don't do this often (or for a long time), it should be possible to completely destroy the whole setup with `inv terminate_ecs` and recreate with `inv create_ecs`.

## Secrets

Deployment assumes that all secret keys (e.g. database password) are stored on **AWS EC2 Parameter Store**. There is no way to get these secrets from outside the VPC. Best is to use the AWS console to set new parameters when needed. See [https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-paramstore.html](documentation).

The Django settings file implements a `get_secret()` funtion that will either get values from environment variables if in development mode, or from the parameter store in production.

## RDS Database

The main Django database is managed by **AWS RDS** using Postgress 9.6 and configured in a multi-region configuration. Unfortunately, the database was not originally created with encryption at rest, and we have not been able to fix that (as there is no easy way to change that).

If we had to create a new database, we would use `inv create_rds_instance`.

This database is fully managed by AWS, so there is currently no required maintenance on our part.

## Redshift

The second database is used purely to store stream data and it utilizes a secondary database currently implemented with **AWS Redshift** (although from Django's stand point, this is just a second Postgress database).

The original redshift database was created with `inv create_redshift_cluster` but was not configured with encryption enabled.

Some work was done to allow us to create a third databse (second Redshift) for an improved TimeSeries database. The function to create this second redshift database (with encryption enabled) is `inv create_streamtimeseries_redshift`. NOTE this database is currently NOT in production (or life).

## DynamoDB

**AWS DynamoDB** is currently only used for:

- **Worker Log** (iotile-worker-logs-{stage}) stores one entry for every worker task that is processed.
- **Filter Log** (iotile-filter-log-{stage}) stores one entry for every StreamFilter that gets executed.

Both tables are provisioned with auto scaling enabled.

## ElasticSearch

A small ElasticSearch instance is used to speed up searches within IOTile Cloud. This database is fully managed by **AWS ElasticSEarch** and was created manually using the AWS console with basic defaults.

## Redis Cache

A small Redis Cache is used to cache database data when needed and also as a NoSQL database for some non-escential features.

This database is fully managed by **AWS ElasticCache** and was created with `inv create_redis_cluster`

## Kinesis Firehose

To allow for higher throughput, we enable **AWS Kinesis Firehose**, which was created with `inv create_firehose_stream`.

There is a secondary Firehose setup to work with the new improved TimeSeries Redshift instance, but it is also not currently in use.

## S3 Buckets

IOTile Cloud uses **AWS S3* buckets for many things. From storing the Web's static files (CSS/JS/Images) which are cached via CloudFront, to a number of buckets used to store different data.

Here is a list of current buckets:

### iotile-cloud-statics

Has a single sub-directory, `static` which is cached on https://cdn.iotile.cloud/statitc/ via CloudFront.

### iotile-cloud-media

This directory is currently cached to https://media.iotile.cloud via CloudFront.

Has a directory for every server type (**prod**, **stage** and **dev**), and each holds the corresponding data for:

- **incoming** has permissions to allow us to upload logos and avatars used by the s3image Django application. Files uploaded to this directory trigger an **AWS Lambda** function to resize these images into a tiny, small and medium size file which is then uploaded to the **images** directory.
- **images** has the resized images used when rendering HTML pages with these images.
- **s3file** contains all files uploaded by the s3file Django application and as of this writing, includes:
  - **firmware**: firmware update files (no longer use)
  - **notes**: Images uploaded as part of StreamNotes
  - **scripts**: trub files used for OTA
  - **sg** Device Sensor Graphs uploaded (not used for anything rigth now)
  - **sxd**: Landsmond SXd Saver files that we allow customers to upload

### iotile-cloud-reports

Has a directory for every server type (**prod**, **stage** and **dev**), and each holds the corresponding data for Generated Reports.

Each of these reports is organized under its Organization folder.

### iotile-cloud-stream-event-data

Has a directory for every server type (**prod**, **stage** and **dev**), and each holds the corresponding data for StreamEventData data files (e.g. all Accelerometer waveform Json files).

Data is stored by year/month/day/hour and the event.uuid.

### iotile-cloud-streamers and iotile-streamer-dropdown

Has a directory for every server type (**prod**, **stage** and **dev**), and each holds the corresponding data for rwa Streamer Reports that are uploaded.

All current streamer reports get uploaded to **iotile-streamer-dropdown** before they get proecssed by the backend workers. Files are organized by streamer slug.

Streamer repports that cannot be parsed are still loaded under an `errors` directory on **iotile-cloud-streamers**

(Should be cleaned at some point)

### iotile-stream-in

AWS Kinesis Firehose requires a bucket to be defined for all the stream data to be placed while loading to Firehose. I basically stores a second copy of the streamer report data, but in the JSon format required by firehose/redshift to work.

### iotile-timeseries-kinesis

This is the equivalent Firehose bucket for the new TimeSeries Redshift database (currently not used).


## AWS Lambda Functions

Several lambda functions are used for different functionality in an effort to keep the main serves from doing work. We use the [Serverless Framework](https://serverless.com/) to create and manage these functions. Most functions are defined under the [serverless](../serverless) directory.

Note that the infrastructure also uses some Lambda function defined on the [iotile-custom-filters](https://github.com/iotile/iotile-custom-filters) repo.

There is also an old, unused lambda function (not using the Serverless Framework) under [/lambdas](../lambdas) that could be used to authorized if we wanted to create a lambda based API gateway with the same JWT token as used by the IOTile Cloud API.

Current acive functions:

### health

This is a collection of lambda functions used to check the health of the infrastructure. It mostly schedules different worker tasks

It defines the following associated infrastructure:

- **cloud.iotile.serverless.health** S3 bucket for deployment
- The following **AWS Cloudwatch** cron jobs:
  - **hour-worker-check-${stage}** to call **publish_worker_healthcheck()** every hour to check workers
  - **device_check-${stage}** to schedule a **DeviceStatusCheckAction** worker task to check for Device Status
  - **hour-stream-data-check-${stateg}** to schedule **HealthCheckStreamDataAction** to check if there is StreamData in the future
  - **day-clean-up-${stage}** to call fucntion to cleanup worker logs so we only keep one month of tasks.
  - **day-collect-stats-${stage}** to schedule a **WorkerCollectStatsAction** to collect worker stats.
  - **day-collect-dbstats-${stage}** to schedule a **DbStatsAction** to collect daily stats (e.g. number of records in StreamData).

### process-upload-sxd

This function automatically runs **SXDFileParser** and **TripUploader** when a user uploads an SXd file.

The function is triggered by the **iotile--upload-sxd--${stage}** SNS topic

### s3image

This is currently the only NodeJs function (as the first one before Python was supported).

This function is triggered by object creations on the **iotile-cloud--media/prod/imcoming** bucket.

This function uses the **iotile-cloud-serverless-s3image-${stage}** S3 bucket for deployment.

### utils

This is a collection of lambda functions to help with different tasks. Currently:

- **deleteS3Obj** triggered by **iotile--delete-s3--{state}** to delete s3 files

Uses the **cloud.iotile.serverless.utils** S3 bucket for deployment.

## SNS Notifications

In addition, some functions are created by other repos. In particular, all custom filter functions (for a given customer/application) are defined under [iotile-custom-filters](https://github.com/iotile/iotile-custom-filters).

All message based notifications are done using **AWS SNS**. We currently use the following topics. Most topics were created manually. Others were automatically created by the Serverless Infrastructure.

- **SESIssues** to get SES notifications on email delivery issues
- **StaffNotifications** used by the Django apps as a simple way to send notifications to IOTile Cloud Staff. DevOps people need to be subscribed to this topic to receive emails.
- **IotileCloudEBNotifications** used to get notification on ElasticBeanstalk deployment or alarms.
- **iotile--delete-s3--{stage}** Used to trigger an AWS Lambda function to delete an S3 file.
- **iotile--upload-sxd--{stage}** Used to trigger an AWS Lambda function to process an uploaded SXd file.
- **dyanmodb** Used to get notificaitons on DynamoDb issues.

## Email Notifications

All customer email notification are handled by **AWS SES**.

The email is configured under **notify.iotile.cloud** as domain, and was created manually using the AWS console with basic defaults, but with DKIM setup.

## SQS messages

The server communicates with the backend workers via an **AWS SQS** queue. The following are the existing queues:

- **iotile-worker-{stage}** is used to send tasks to the main Django based workers
- **iotile-report-{stage}** is used to send tasks to the analytics workers (Wokers infrastructure is defined and created from the arch-analytics code base).

## Content Distribution Network (CDN)

Our CDN is implemented using **AWS CloudFront**. The followinf distributions were manually created:

- **DistributioID=E3VXQQ8PVQ0SWZ**: IOTileCloud Media
- **DistributionID=E1N3SEVFZEXIM0**: IOTileCloud Statics

## DNS

The IOTile Cloud domain is managed by **AWS Route 53** which was created and managed directly from the AWS console.

## SSL Certificate

The iotile.cloud domain SSL certificate was manually created and is managed by **AWS Certificate Manger** and are automatially renewed.


## Authentication roles

### AIM Groups

- **IOTileDevGroup** should be used for all developers

### AIM roles

- **IOTileProductionRole** is the main production role used by EC2 machines
- **ECSInstanceIotileRole** is the role used by ECS instances
- **aws-elasticbeanstalk-ec2-role** is the main elasticbeanstalk role

### AIM Policies

- **IOTileDevPolicy** is used by Strato developers to develop on their local machines/docker
- **iotileProductionPolicy** defines most of the production permissions
- **IotileCloudProductionCredentialsPolicy** gives permissions to the EC2 Parameter Store
- **iotile-streamer-upload-{stage}** is used to give upload only permission to the iotile-streamer-dropbox s3 bucket.
- **iotile-search-{stage}** is used to give access to ElasticSearch

## Sentry

[Sentry](https::/sentry.io) is used to manage exceptions notifications. The IOTile exceptions are under

https://sentry.io/organizations/arch-systems/issues/?project=187085

## Google API

Google API is used for:

- Implement our Maps
- Recaptcha
