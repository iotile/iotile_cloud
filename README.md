# IOTile Cloud by Arch

This is a reference design to implement a solution equivalent to Arch System's https://iotile.cloud

It is a clone of the real source code, but without any Arch sensitive information.

The server can be run on any computer that supports Docker, but some features do have dependencies
on AWS S3. A lot of the code used to deploy to AWS is included, but not very well documented, and
may require a lot of changes to adapt to a given AWS account.

Project is built with Python v3.8+ using the Django Web Framework (v3.2+)

## IOTile Cloud Database Models

IOTile Cloud was originally build by Arch Systems to support the IOTile Platform
(See [IOTile CoreTools](https://github.com/iotile/coretools)).
It is a fairly generic IOT solution, but very influenced by the requirements of the **IOTile Platform**.
And a portion of the feature set is specific to suppoprt IOTile Devices (or anything using the
[IOTile CoreTools](https://github.com/iotile/coretools) python package).

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
  In an AWS implementation, each `StreamEventData` can be associated with an S3 file (a complex data file or image for example) and also contains a `JsonField`
  to represent summary data associated to the complex file in S3. The S3 file is represented with the `S3File` model.
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
* A slug (word which comes from Blog servers and represents "the part of a URL that identifies a particular page on a website in an easy-to-read form") is used
  by Projects, Devices, StreamId to represent a globally unique ID (we call them slugs as the format is URL friendly). These slugs have a letter to represent
  the type of object, followed with a hex representation of the database's primary ID, broken in blocks of four hex numbers (for readibility).
  Some assume 32bits while others represent 64bits:
  * A Project is represented with the letter `p` and a 32bit hex number: `p--00000-0001`
  * A Device is represented with the letter `d` and a 64bit hex number: `d--0000-0000-0000-0001`. For Arch IOTile Devices, this ID also acts as the device's
    Serial Number (S/N). Note that we only use 48 out of the 64 bits, as the last 16 bits are used to represent `DataBlocks` which are models that represent
    archived device data (all the stream data and stream event data associated with a device for a time range).
  * A Variable is represeted with a `v`, the 32bit hex number for the project the variable is associated with, and a 16bit hex number representing the type
    of data (the variable). For example, `5001` is by POD-1G devices to represent water volume (on a water meter). To make the variable globally unique, it
    needs to be associated to a project. This is because while Arch may use `5001` for example, to represent water volume, the variable can represent anything.
    The 16bits that represent a variable are defined in the device's sensor graph, so it can represent whatever the sensor Graph author chooses. The only
    requirement is that whatever the variable represents, it has to be consistent within all devices claimed within a project. Therefore, to make these variables
    globally unique, they require both the project and the 16bit hex: `v--0000-0001--5001` represents variable `5001` within project `1`.
  * As said above, a stream is represented with the required 64bit Device ID and the 16bit variable ID, as well as the 32bit Project ID to allow us to
    differenciate a stream from a device that was under one project and then is moved to another project. Because the same variable IDs could represent
    different things, we need to add the Project to give them context. The Stream slug is then represented like `s--0000-0001--0000-0000-0000-0002--5001`
    which represents variable `5001` (water volume for POD-1Gs) for Device `2` when claimed under Project `1`.
* A number of generic models are used to add meta data to the different objects:
  * `GenericProperties` represent name/value pairs that can be associated with any `Device` or `Project` by setting their target to either the device or project slugs.
  * `ConfigAttributes` are more complex Json objects that can also be associated with  `Device` or `Project`, as well as an `Org` or an `Account` (User). These records
    can be used to store any generic configuration that an application may need to store general configuration. `ConfigAttributes` follow a priority scheme, so
    for example, when asking a device for a given configuration, if not defined at the device level, the API will check the device's project, then the Org, and
    finally the User, until the configuration is found. Different from `GenericProperties` which take a string as `name`, `ConfigAttributes` use a pre-defined
    `name` which is based on the `ConfigAttributeName` model. `ConfigAttributeName` should follow a `:foo:bar` naming scheme (only the first `:` is required).
  * `StreamNotes` represent text that is associated to a `StreamId`, `Device` or `Project` and can be used to store logs or user comments.
  * A `DeviceLocation` can be used to store the GPS coordicates of a `Device` at a given time.
  * A `DeviceKey` can be used to store secret keys (e.g. SSH or decryption tokens) associated with a given device.
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
* `DataBlocks` models are used to represent data archives. This is particular relevant for POD-1M devices, which are used to as data loggers
  for shipping packages. In this case, the data associated with a Device represents a trip, but in order to reuse the same device for a second
  trip, the data from the first trip is archived. This is done by basically updating all the data to a new stream ID where the Device 64bit ID
  actually represents a `DataBlock`. This is only 48bits of the 64bits are used to represent the actual device. the last 16bits are used to
  represent the archives for the given device, so if `d--0000-0000-0000-0001` represents Device `1`, `b--0001-0000-0000-0001` represents
  archive `1` for device `1`. When archiving this data, we change the stream slug from `s--0000-0001--0000-0000-0000-0002--5001`
  to `s--0000-0001--0001-0000-0000-0002--5001`.
* `UserReport` and `GeneratedUserReport` are models that help generate custom reports. A generated report is one that is generated as a worker
  task, and then uploaded to S3 as a stand alone report. These reports can be in the form of stand-alone HTML files (e.g. using bokeh),
  CSV files or XLSX files. The `UserReport` acts as a template, which allows the UI  to present the options to the user. When a user
  clicks on the generation button, a `GeneratedUserReport` is created with `status='GS'` ("Scheduled...") and a task is scheduled to process
  this report. When the task is processed, the `GeneratedUserReport` record is found and used to determine which custom generator to use.
  The generator is then called to generate the report, upload it to S3, and set the report `status='G1'` ("Report Generation Completed").
  Available generators can be found on `server/apps/report/generator`. Each generator has a `forms.py` with a custom Django Form to
  collect appropiate options from the user during the generation request (which are then stored as Json on `UserReport.config`),
  and a `generator.py` with a class that derives from `ReportGenerator`, and defines a `generate_user_report` method, and a `urls.py`
  with definitions to define any required configuration flow. New genrators can
  be added by just creating new generator packages, and updating the `UserReport.FORMAT_CHOICES` constant in the `models.py` file.

## Server Architecture

The IOTile Cloud is a Django server that uses the following services:

* `database1` is a Postgres database and is used to store all the basic User, Org, Project, Device, Stream and associated meta data.
* `database2` is a second Postgres database (can also be deployed to AWS Redshift) specialized to store all the actual stream data and
  stream event data. Depending on the number of devices, this is the database that will need to be optimized to handle a large number
  of writes as a lot of devices could stream data at the same time.
* A `redis` database is used to cache data when possible to minimize SQL database queries
* An `elastic search` database is used to power the search enginer, and allow users to easily find Device, Projects, Properties and other
  meta data.
* This project does not use Celery to implement async worker tasks (long story) and instead implements its own solution based on the
  `Action` class (see `server/apps/sqsworker`). The worker queue is implemented with AWS SQS (and using `elasticmq` when running locally)
  * Similar to a celery worker, the worker uses the same Django project, but runs as a management function:
    * `python manage.py sqs-loop-worker` (see `supervisord.conf`)
  * All worker tasks are implemented on `/server/apps/*/worker/` packages and using classes that derive from the `Action` class and implement
    a `schedule` class method and a `execute` method. The `schedule` method will post an SQS message with a json object with a `Dict`
    representing the required arguments for the given worker task. When the SQS message is processed by the worker, it will call the
    `execute` method and pass the `Dict` that was sent by the `execute` method.
* When enabled and deployed to AWS, a `DynamoDB` database is used to log worker tasks. (`USE_DYNAMODB_WORKERLOG_DB=True`)

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
* iotile.cloud uses several AWS services, so the AWS deployment instructions assume you will do to:
  * AWS Elasticsearch to implement the elastic search engine
  * AWS Elasricache to implement Redis
  * AWS RDS to implement `database1`
  * AWS Redshift to implement `database2`
  * AWS S3 for storing `StreameReports` and `S3File` files used by `StreamEventData` (as well as `S3Image` files used for Org logos)
  * Uses DynamoDB for logging
    * Uses peopleperhour/dynamodb when running locally
* It is important to note that the docker-compose based server may requires AWS S3 for some feature
  (e.g. Uploading `StreamerReports`, uploading `StreamEventData` with `S3File` content or uploading Org logos)
  * But data can still be uploaded via the APIs for example, so most of the key functionality should be avaiable without AWS.
* Use the [python_iotile_cloud Python SDK](https://github.com/iotile/python_iotile_cloud) to help write python scripts
  to interact with the Server's Rest API.

## AWS Deployment

As said above, this is a reference design more than a plug and play solution, especially when it comes to the deployment instructions.
We are unable to ensure that the instructions will work or be kept upto date, and we are unable to help much in terms of issues with
the deployment instructions (so yes, you are on your own if you want to try to use them).

See `docs/` for a partial set of instructions

## Development Instructions

While it is possible to run the server with the host's native Python environment, it is highly recommended to
use Docker for testing and development. A set of [Python Invoke](https://www.pyinvoke.org/) tasks are defined
to make this process easy. Both running tests or running a local server usually require a single `inv` command.

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
# Build containers (required when dependencies change)
inv test -a build
# Run full test
inv test -a signoff
# Run a single app test
inv test -a custom -p ./apps/org
# Stop test containers without destroying them
inv test -a stop
# Destroy all containers
inv test -a down
```

### Running Server

To run the local server, you use the `run-local` task:

```bash
# Run server in background
inv run-local -a up
# Stop server, but without destroying databases
inv run-local -a stop
# Kill all containers and destroy databases
inv run-local -a down
# Watch a given container's STDOUT (logs)
inv run-local -a logs-web
inv run-local -a logs-worker
inv run-local -a logs-nginx
# Rebuild images (usually not needed as source files are cross mounted)
# But required for sure if dependencies change
inv run-local -a build
```

### Development

To make migrations and/or migrate

```bash
# Make new migrations
inv run-local -a makemigrationss
# Migrate
inv run-local -a migrate
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
