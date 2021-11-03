

# IOTile Cloud by Arch

Project is built with Python3 using the Django Web Framework (v2+)
Original template was based on django-aws-template (https://github.com/dkarchmer/django-aws-template)

This project has the following basic features:

* Custom Authentication Model with django-allauth
* Rest API with Django Rest Framework with JWT tokens
* Caching with Django Redis
* Improved user interface for forms using Django Crispy Forms
* Search capabilities with Django Elasticserach DSL
* Email notifications using AWS SES and Django SES

## Installation

### Assumptions

You must have the following installed on your computer

* Python 3.6 or greater
* Docker

For MacOS, see https://gist.github.com/dkarchmer/d8124f3ae1aa498eea8f0d658be214a5

### Python Environment

To set up a development environment quickly, first install Python 3. It comes with virtualenv built-in. So create a virtual env by:

```
$ python3 -m venv  ~/.virtualenv/iotile_cloud
$ .  ~/.virtualenv/iotile_cloud/bin/activate
$ pip install -U pip
$ pip install -r requirements.txt
```

### Secret Keys

As per security best practices, secret credentials/keys should never be stored under version control.

Get the proper `.local-env`, `.docker.env` and place them under `server/config/settings`.
If you cannot get a copy, just used the `sample-*.env` files under the same directory, and modify as needed.

For production, all critical secret keys are stored on AWS SSM Parameter Store, making it 
easy to deploy to AWS without having to store secret keys on local machines. The Django 
settings file gets all these keys from the Parameter Store, assuming the AWS IAM role
has access to such keys.

#### AWS Credentials

Requires awscli V2 installed:

```bash
# Installing latest AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
rm -rf awscliv2.zip aws
```

To create an AWS Profile, do

```bash
aws configure
```

and follow the instructions. Select `us-east-1` as your region, and use enter the credentials associated to
your AWS account (ask release manager to generate a set if required).

For development, the AIM User should be part of the IOTileCloudDevelper Group

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
