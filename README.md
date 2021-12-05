# IOTile Cloud by Arch

This is a reference design to implement a solution equivalent to Arch System's https://iotile.cloud

It is a clone of the real source code, but without any Arch sensitive information.

The server can be run on any computer that supports Docker, but some features do have dependencies
on AWS S3. A lot of the code used to deploy to AWS is included, but not very well documented, and
may require a lot of changes to adapt to a given AWS account.

Project is built with Python v3.8+ using the Django Web Framework (v3.2+)

## IOTile Cloud features

IOTile Cloud was originally build by Arch Systems to support the IOTile Platform
(See [IOTile CoreTools](https://github.com/iotile/coretools)).
It is a fairly generic IOT solution, but very influenced by the requirements of the **IOTile Platform**.

* The `Org` model represent Companies or entities within a company
* The `Account` model represents users
* Users can be members of one or more organization via the `OrgMembership` model.
* Users can be invited to a new Organization with an `Invitation` object (and flow).
* The `Device` model represents IOTile PODs or any other IOT device uploading data to the server.
* Devices are **claimed** under a `Project` which is owned by an Organization. A claimed device is a device that is owned by a given organization
* Projects are nothing more than ways to group together a number of devices that are used to measure similar metrics. 
  Think of a Project as the spreadsheet you would create if you had number of devices that send the same sensor data (e.g. Temperature and Pressure).
* Devices upload data in the form of `StreamData` or `StreamEventData`. 
  The difference is that `StreamData` represents simple timeseries data (`id`, `timestamp`, `value`) while `StreamEventData` represent complex data objects
  In an AWS implementation, each `StreamEventData` can be associated with an S3 file (a complex data file or image for example) and alsocontains a `JsonField`
  to represent summary data associated to the complex file in S3.
* `StreamData` (as `StreamEventData`) is represented with a single table, and is therefore associated to a `StreamId` which acts as a header with meta data
  required to identify and interpret the data. A `StreamId` is identified with a `ID` or `Slug` (More about `Slugs` below) that is built off 1) A `Project` slug,
  2) A `Device` slug and 3) A `Streamvariable` slug. Stream IDs look like `s--0000-0001--0000-0000-0000-0002--5001` as an example which represent water meter data
  (`5001`) for device `0x0002` claimed by project `0x0001`.
* A `Device` is defined by its `DeviceTemplate` which represents the physical characteristics of the IOT device, and a `SensorGraph` which is an IOTile concept and
  represents the application configured. The `SensorGraph` for example, determines the type of `StreamVariable` (known as `streams` within the IOTile Platform)
  that the given device is capable of producing. For more on sensor graphs,
  see [Introduction to Sensor Graphs](https://coretools.readthedocs.io/en/latest/tutorials.html#introduction-to-sensorgraph).
* `DeviceTemplates` that represent IOTile Devices have one or many `Components` which represent the physical **HW tiles** which are the building blocks of
  an IOTile Device.
* A number of generic models are used to add meta data to the different objects: 
  * `GenericProperties` represent name/value pairs that can be added to any `Device` or `Project` by setting their target to either the device or project slugs.
  * `ConfigAttributes` are more complex Json objects that can also be added to a `Device` or `Project`, as well as an `Org` or an `Account` (User). These records
    can be used to store any generic configuration that an application may need to store general configuration. `ConfigAttributes` follow a priority scheme, so
    for example, when asking a device for a given configuration, if not defined at the device level, the API will check the device's project, then the Org, and
    finally the User, until the configuration is found. Different from `GenericProperties` which take a string as `name`, `ConfigAttributes` use a pre-defined
    `name` which is based on the `ConfigAttributeName` model. `ConfigAttributeName` should follow a `:foo:bar` naming scheme (only the first `:` is required).
  * `StreamNotes` represent text that is associated to a `StreamId`, `Device` or `Project` and can be used to store logs or user comments.
  * A `DeviceLocation` can be used to store the GPS coordicates of a `Device` at a given time.
* A `StreamAlias` can be used to dynamically build a virtual stream with sections from different physical streams.
  It is constructed based on a list of `StreamAliasTap` records which basically represent is a timestamped pointer to a physical stream.
  A list of `StreamAliasTaps` can be used to construct a virtual stream from different data streams.
* A `Fleet` is a group of devices, and it is used to help with any over-the-air (OTA) flow. The OTA is represented with:
  * A `DeploymentRequest` is used to initiate a request to update a given `Fleet` with a given `DeviceScript` whichcan represent the set of
    commands the device needs to run to update itself
  * A `DeploymentAction` is created once the edge device (or computer) attempts to send the OTA instructions to the device.
    Within the IOTile platform, a record posted from a phone or gateway indicating that that device attempted to update an IOTile device with
    a `DeviceScript` based on a `DeploymentRequest`.
    This is not definitive, that confirmation will come from a value posted by the device’s sensor graph. i.e. the actual confirmation comes in the
    form of a `StreamData` record using either a `5c08` (`OS_TAG_VERSION`) or `5c09` (`APP_TAG_VERSION`) stream variables.
  * Note that the OTA flow was built and it is intended to be used with an IOTile device and ideally using `IOTile`
    [coretools](https://coretools.readthedocs.io)
* When uploading IOTile Device data, the device sensor graph will upload data using a `Streamer`. `Streamer` data is
  uploaded using `StreamerReports`.
  See [Understanding IOTile Reports](https://coretools.readthedocs.io/en/latest/tutorials.html#understanding-iotile-reports) for more on
  streamer reports.
* Note that support for `StreamReports` requires an AWS S3 bucket, as all uploaded files get stored on S3 before a worker is scheduled to
  parse the data and write it to the `StreamData` or `StreamEventData` tables.

## Server Architecture

The IOTile Cloud is a Django server that uses the following services:

* `database1` is a Postgres database and is used to store all the basic User, Org, Project, Device, Stream and associated meta data.
* `database2` is a second Postgres database (can also be deployed to AWS Redshift) specialized to store all the actual stream data and
  stream event data. Depending on the number of devices, this is the database that will need to be optimized to handle a large number
  of writes as a lot of devices could stream data at the same time.
* A `redis` database is used to cache data when possible to minimize SQL database queries
* An `elastic search` database is used to power the search enginer, and allow users to easily find Device, Projects, Properties and other
  meta data.
* This project does not use Celery to implement asynh worker tasks (long story) and instead implements its own solution based on the
  `Action` class. The worker queue is implemented with AWS SQS (and using `elasticmq` when running locally)
  * Similar to a celery worker, the worker uses the same Django project, but runs as a management function:
    * `python manage.py sqs-loop-worker` (see `supervisord.conf)
  * All worker tasks are implemented on `worker/` app sub-packages and using classes that derive from the `Action` class and implement
    a `schedule` class method and a `execute` method. The `schedule` method will post an SQS message with a json object with a `Dict`
    representing the required arguments for the given worker task. When the SQS message is processed by the worker, it will call the
    `execute` method and pass the `Dict` that was sent by the `execute` method.
* When enabled and deployed to AWS, a `DynamoDB` databse is used to log worker tasks. (`USE_DYNAMODB_WORKERLOG_DB=True`)

## User features

* The server supports social login which is impleneted with [django-allauth](https://django-allauth.readthedocs.io/en/latest/installation.html)
* Most models have a Rest API implemented with [django-rest-framework](https://www.django-rest-framework.org/)
* The server UI is implemented using a Bootstrap based template (see `webapp/`).
* Improved user interface for forms using Django Crispy Forms
* Search capabilities with Django Elasticserach DSL
* Email notifications using AWS SES and Django SES

## Developer Features

Most of the code required to deploy iotile.cloud via AWS was left but more as a reference.

* Custom worker scheme using AWS SQS as message queue
  * Uses s12v/elasticmq when running locally
* Ready for deployment using AWS Elasticsearch and AWS ECS for workers
* Uses AWS S3 for file storage
* Production deployment requires AWS RDS and AWS Redshift for SQL databases
* production deployment requires AWS Elasticache and AWS Elasticseach
* Uses DynamoDB for logging
  * Uses peopleperhour/dynamodb when running locally
* Local server uses Docker Compose, but requires AWS S3 and AWS SQS

## AWS Deployment

As said above, this is a reference design more than a plug and play solution, especially when it comes to the deployment instructions.
We are unable to ensure that the instructions will work or be kept upto date, and we are unable to help much in terms of issues with
the deployment instructions (so yes, you are on your own if you want to try to use them).

See `docs/` for a partial set of instructions

## Development Instructions

### Assumptions

You must have the following installed on your computer

* Python 3.8 or greater
* Docker and Docker Compose

For MacOS, see https://gist.github.com/dkarchmer/d8124f3ae1aa498eea8f0d658be214a5

### Python Environment

To set up a development environment quickly, first install Python 3. It comes with virtualenv built-in. So create a virtual env by:

```bash
python3 -m venv  ~/.virtualenv/iotile_cloud
.  ~/.virtualenv/iotile_cloud/bin/activate
pip install -U pip
pip install -r requirements.txt
```

### Secret Keys

As per security best practices, secret credentials/keys should never be stored under version control.

Get the proper `.local-env`, `.docker.env` and place them under `server/config/settings`.
If you cannot get a copy, just used the `sample-*.env` files under the same directory, and modify as needed.

For production, all critical secret keys are stored on AWS SSM Parameter Store, making it
easy to deploy to AWS without having to store secret keys on local machines. The Django
settings file gets all these keys from the Parameter Store, assuming the AWS IAM role
has access to such keys.

### Static Files

Static files are built different from any traditional Django project. Before tests can be run
or a local server can be started, static files have to be built

To build static files, use

```bash
inv build-statics
```

### Testing

For testing, you must use the config/settings/test.py settings file:

```bash
inv test -a signoff
inv test -a custom -p ./apps/org
```

### Running Server

Run docker-compose based server with

```bash
inv run-local -a up
```

### Development

To make migrations

```bash
inv run-local -a makemigrationss
```

### Updating requirements

This projects use [pip-tools](https://github.com/jazzband/pip-tools) to manage requirements. 
Lists of required packages for each environment are located in `*.in` files, and complete pinned 
`*.txt` files are compiled from them with `pip-compile` command:

```bash
cd server 
pip-compile requirements/base.in
pip-compile requirements/development.in
```

To update dependency (e.g django) run following:

```bash
pip-compile --upgrade-package django==3.1 requirements/base.in
pip-compile --upgrade-package django==3.1 requirements/development.in
```
