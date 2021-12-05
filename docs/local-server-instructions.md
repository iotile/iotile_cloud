# How to run a production worthy local server?

This section describes the basic setup to be able to run a production worthy local server using docker compose
and minimum AWS infrastructure (mostly to store files).

## AWS Setup

The docker-compose infrastructure will create all required services except from:

- AWS S3 service
- AWS SNS service (for notificatations)
- AWS Lambda Functions (that handle some part of the infrastructure)

But only S3 is needed for a basic IOTile Platform, so this document describes how to set these buckets.

The server uses a number of S3 buckets (which is sometimes needed to improve security), but it is also possible
(and safe) to use a single bucket. The following explains how to set up the single bucket (similar process is
needed to create any additional buckets).

### Create AWS Bucket

Using ther AWS Console, create a new bucket and make sure to configure like this:

- Go to "Block Public Access" and switch off the "Block all public access" option. This is not needed as
all files will not be visible.
- In the "Bucket policy", enter:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AddPerm",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": [
                "arn:aws:s3:::your-s3-bucket-name/prod/images/*",
                "arn:aws:s3:::your-s3-bucket-name/dev/images/*",
                "arn:aws:s3:::your-s3-bucket-name/stage/images/*"
            ]
        }
    ]
}
```

- In the "Cross-origin resource sharing (CORS)" section, add

```json
[
    {
        "AllowedHeaders": [
            "origin",
            "Content-*",
            "Host",
            "x-amz-acl",
            "x-amz-meta-qqfilename",
            "x-amz-date",
            "authorization"
        ],
        "AllowedMethods": [
            "POST",
            "PUT"
        ],
        "AllowedOrigins": [
            "*"
        ],
        "ExposeHeaders": [
            "ETag"
        ],
        "MaxAgeSeconds": 3000
    }
]
```

### Create IAM Policy

Create a new IAM policy with the following json:

```json
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "BucketAccess",
            "Effect": "Allow",
            "Action": [
                "s3:List*",
                "s3:GetBucketLocation"
            ],
            "Resource": [
                "arn:aws:s3:::your-s3-bucket-name"
            ]
        },
        {
            "Sid": "S3ObjectAccess",
            "Effect": "Allow",
            "Action": [
                "s3:*Object*",
                "s3:List*",
                "s3:AbortMultipartUpload"
            ],
            "Resource": [
                "arn:aws:s3:::your-s3-bucket-name/*"
            ]
        }
    ]
}
```

### Create IAM User

Now we need to create an IAM User with tokens we can use to access the above policy.

Create a new user and make sure you click on the "Access key - Programmatic access" option. On the next
page, click on "Attach existing policies directly" and select the new policy you created in the above
step. Create "next" again and then "Create User".

Make sure to download the CSV file with the necessary tokens.

### Add tockens to project

Go to `server/config/settings` and create a file (if needed) named `.docker.env`

Add the following content

```ini
PRODUCTION=False
DOCKER=True
DEBUG=True
SERVER_TYPE=dev
# Command to create a new secret key:
# $ python -c 'import random; import string; print("".join([random.SystemRandom().choice(string.digits + string.ascii_letters + string.punctuation) for i in range(100)]))'
SECRET_KEY=a-very-long-tokenr-using-above-command
DOMAIN_NAME=127.0.0.1:9000
DOMAIN_BASE_URL=http://127.0.0.1:9000
COMPANY_NAME=Your Company (Docker)
INITIAL_ADMIN_EMAIL=<admin_email>
AWS_ACCESS_KEY_ID=created_token_key
AWS_SECRET_ACCESS_KEY=created_access_key
# Ignore the following
SNS_STAFF_NOTIFICATION=ignore-for-now
SNS_ARCH_SLACK_NOTIFICATION=ignore-for-now
SNS_DELETE_S3=ignore-for-now
SNS_UPLOAD_SXD=ignore-for-now
STREAMER_REPORT_DROPBOX_BUCKET_NAME=iotile-cloud-foss-test
S3IMAGE_BUCKET_NAME=iotile-cloud-foss-test
S3FILE_BUCKET_NAME=iotile-cloud-foss-test
REPORTS_S3FILE_BUCKET_NAME=iotile-cloud-foss-test
STREAM_EVENT_DATA_BUCKET_NAME=iotile-cloud-foss-test
#S3IMAGE_CDN=https://media.test.com
STREAMER_REPORT_DROPBOX_PRIVATE_KEY=created_access_key
STREAMER_REPORT_DROPBOX_PUBLIC_KEY=created_token_key
# FineUploader (Stream Upload)
STREAM_INCOMING_PRIVATE_KEY=created_access_key
STREAM_INCOMING_PUBLIC_KEY=created_token_key
S3IMAGE_PRIVATE_KEY=created_access_key
S3IMAGE_PUBLIC_KEY=created_token_key
GOOGLE_API_KEY=changeme
RECAPTCHA_SITE_KEY=changeme
RECAPTCHA_SECRET_KEY=changeme
TWILIO_FROM_NUMBER=changeme
TWILIO_ACCOUNT_SID=changeme
TWILIO_AUTH_TOKEN=changeme
```

## Run Server

At this point, you should be able to run the server and have a working site:

```bash
inv build-statics
inv run-local -a up
```
