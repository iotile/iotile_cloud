"""
Django settings for Strato project.
For more information on this file, see
https://docs.djangoproject.com/en/dev/topics/settings/
For the full list of settings and their values, see
https://docs.djangoproject.com/en/dev/ref/settings/
"""
import datetime
import os
import sys

import boto3
# Use 12factor inspired environment variables or from a file
import environ
from django.contrib import messages

from apps.utils.aws.common import AWS_REGION

# Build paths inside the project like this: join(BASE_DIR, "directory")
BASE_PATH = environ.Path(__file__) - 3
BASE_DIR = str(BASE_PATH)
LOG_FILE = BASE_PATH.path('logs')
TESTING = len(sys.argv) > 1 and sys.argv[1] == 'test'

# List of keys stored on EC2's Parameter Store as:
#       iotilecloud.prod.xxx where xxx is the value in the following MAP
SECRET_MAP = {
    'SECRET_KEY': 'SecretKey',
    'JWT_SECRET_KEY': 'JwtSecretKey',
    'RDS_PASSWORD': 'RdsPassword',
    'GOOGLE_API_KEY': 'GoogleApiKey',
    'RECAPTCHA_SITE_KEY': 'RecaptchaSiteKey',
    'RECAPTCHA_SECRET_KEY': 'RecaptchaSecretKey',
    'STREAMER_REPORT_DROPBOX_PUBLIC_KEY': 'DropboxPublicKey',
    'STREAMER_REPORT_DROPBOX_PRIVATE_KEY': 'DropboxPrivateKey',
    'S3IMAGE_PUBLIC_KEY': 'S3ImagePublicKey',
    'S3IMAGE_PRIVATE_KEY': 'S3ImagePrivateKey',
    'SEARCH_ACCESS_KEY_ID': 'SearchAccessKey',
    'SEARCH_SECRET_ACCESS_KEY': 'SearchSecretAccessKey',
    'SENTRY_DSN': 'SentryDns',
    'TWILIO_AUTH_TOKEN': 'TwilioAuthToken',
    'TWILIO_ACCOUNT_SID': 'TwilioSID',
}

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    RECAPTCHA_PUBLIC_KEY=(str, 'Changeme'),
    RECAPTCHA_PRIVATE_KEY=(str, 'Changeme'),
    SERVER_TYPE=(str, 'dev'),
    PRODUCTION=(bool, False),
    DOCKER=(bool, False),
    DOMAIN_NAME=(str, 'changeme.com'),
    DOMAIN_BASE_URL=(str, 'https://changeme.com'),
    WEBAPP_BASE_URL=(str, 'https://changeme.com'),
    SITE_NAME=(str, 'IOTile Cloud by Arch'),
    CACHE_URL=(str, None),
    REDSHIFT_DB_NAME=(str, 'needdb'),
    USE_WORKER=(bool, False),
    DYNAMODB_URL=(str, None),
    METRICS_CACHING_DISABLE_DEBUG_NOTIF=(bool, True)
)

SITE_ID = 1

# Use Django templates using the new Django 1.8 TEMPLATES settings
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'templates'),
            # insert more TEMPLATE_DIRS here
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                # list if you haven't customized them:
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.request',

                # Insert your TEMPLATE_CONTEXT_PROCESSORS here or use this
                'apps.utils.context_processor.basics',
                'apps.utils.context_processor.site',
                'apps.org.context_processor.active_org',
                'apps.project.context_processor.active_org',
            ],
        },
    },
]

# Ideally move env file should be outside the git repo
# i.e. BASE_DIR.parent.parent
env_file = None
if not env('PRODUCTION') and not env('DOCKER'):
    os.environ['DJANGO_ENV_FILE'] = '.local.env'
if 'DJANGO_ENV_FILE' in os.environ:
    env_file = os.path.join(os.path.dirname(__file__), os.environ['DJANGO_ENV_FILE'])
    if os.path.isfile(env_file):
        print('Reading Env file: {0}'.format(env_file))
        environ.Env.read_env(env_file)
    else:
        print('Warning!! No .env file: {0}'.format(env_file))
        # sys.exit(0)

ADMINS = (
    # ('Username', 'your_email@domain.com'),
    # TODO: Replace with your own admin email(s)
    ('admin', 'admin@test.com'),
)

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/dev/howto/deployment/checklist/

PRODUCTION = env('PRODUCTION')
SERVER_TYPE = env('SERVER_TYPE')

if PRODUCTION:
    # For Production, all secret keys are stored on EC2's Parameter Store
    ssm = boto3.client('ssm', region_name=AWS_REGION)

    def get_secret(key):
        ssm_key = '.'.join(['iotilecloud', SERVER_TYPE, SECRET_MAP[key]])
        resp = ssm.get_parameter(
            Name=ssm_key,
            WithDecryption=True
        )
        secret = resp['Parameter']['Value']
        return secret
else:
    # For all other cases, secrets are stored on env variables
    def get_secret(key):
        return env(key)

SECRET_KEY = get_secret('SECRET_KEY')
SITE_NAME = env('SITE_NAME')
DOCKER = env('DOCKER')
DOMAIN_NAME = env('DOMAIN_NAME')
DOMAIN_BASE_URL = env('DOMAIN_BASE_URL')
WEBAPP_BASE_URL = env('WEBAPP_BASE_URL')
USE_WORKER = env('USE_WORKER')
ALLOWED_HOSTS = []
COMPANY_NAME = 'Your Company.'
if not PRODUCTION:
    COMPANY_NAME += ' ({})'.format(SERVER_TYPE)

DYNAMODB_URL = env('DYNAMODB_URL')

print('PRODUCTION = {0}, SITE_NAME={1}'.format(PRODUCTION, SITE_NAME))

# Application definition

DJANGO_APPS = (
    'django.contrib.auth',
    'django.contrib.admin',
    'django.contrib.contenttypes',
    'django.contrib.sites',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.postgres',
)

THIRD_PARTY_APPS = (
    'django_ses',
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_api_key',
    'allauth',
    'allauth.account',
    'corsheaders',
    'captcha',
    'crispy_forms',
    'django_filters',
    'drf_yasg',
    'health_check',
    'health_check.db',
    'health_check.cache',
    # 'health_check.contrib.s3boto_storage',
    'django_elasticsearch_dsl'
)

# Apps specific for this project go here.
COMMON_APPS = (
    'apps.authentication',
    'apps.main',
    'apps.org',
    'apps.component',
    'apps.devicetemplate',
    'apps.projecttemplate',
    'apps.sensorgraph',
    'apps.project',
    'apps.physicaldevice',
    'apps.stream',
    'apps.staff',
    'apps.s3images',
    'apps.s3file',
    'apps.widget',
    'apps.streamalias',
    'apps.streamdata',
    'apps.streamevent',
    'apps.streamnote',
    'apps.invitation',
    'apps.streamfilter',
    'apps.devicescript',
    'apps.devicefile',
    'apps.streamer',
    'apps.vartype',
    'apps.sqsworker',
    'apps.property',
    'apps.emailutil',
    'apps.utils',
    'apps.datablock',
    'apps.deviceauth',
    'apps.fleet',
    'apps.report',
    'apps.ota',
    'apps.orgtemplate',
    'apps.configattribute',
    'apps.devicelocation',
    'apps.verticals.shipping',
    'apps.vendor',
)

INSTALLED_APPS = DJANGO_APPS + COMMON_APPS + THIRD_PARTY_APPS

MIDDLEWARE = [

    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'corsheaders.middleware.CorsPostCsrfMiddleware',
    'django_feature_policy.FeaturePolicyMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.utils.timezoneMiddleware.TimezoneMiddleware',
]

ROOT_URLCONF = 'config.urls'

WSGI_APPLICATION = 'config.wsgi.application'

# Database
# https://docs.djangoproject.com/en/dev/ref/settings/#databases

if PRODUCTION:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ['RDS_DB_NAME'],
            'USER': os.environ['RDS_USERNAME'],
            'PASSWORD': get_secret('RDS_PASSWORD'),
            'HOST': os.environ['RDS_HOSTNAME'],
            'PORT': os.environ['RDS_PORT'],
            'CONN_MAX_AGE': 600,
        },
        'streamdata': {
            'ENGINE': 'django_redshift_backend',
            'NAME': env('REDSHIFT_DB_NAME'),
            'USER': os.environ['RDS_USERNAME'],
            'PASSWORD': get_secret('RDS_PASSWORD'),
            'HOST': os.environ['REDSHIFT_HOSTNAME'],
            'PORT': os.environ['REDSHIFT_PORT'],
        }
    }
elif SERVER_TYPE == 'stage':
    DATABASES = {
        'default': env.db('DATABASE_DEFAULT_URL'),
        'streamdata': {
            'ENGINE': 'django_redshift_backend',
            'NAME': env('REDSHIFT_DB_NAME'),
            'USER': os.environ['RDS_USERNAME'],
            'PASSWORD': os.environ['RDS_PASSWORD'],
            'HOST': os.environ['REDSHIFT_HOSTNAME'],
            'PORT': os.environ['REDSHIFT_PORT'],
        }
    }
else:
    DATABASES = {
        # Raises ImproperlyConfigured exception if DATABASE_URL not in
        # os.environ
        'default': env.db('DATABASE_DEFAULT_URL'),
        'streamdata': env.db('DATABASE_STREAMDATA_URL'),
    }

DATABASE_ROUTERS = [
    'apps.dbrouter.streamdata.StreamDataRouter',
    'apps.dbrouter.default.DefaultRouter',
]

# pprint.pprint(DATABASES)

if PRODUCTION:
    redis_hostname = os.environ['REDIS_HOSTNAME']
    redis_port = os.environ['REDIS_PORT']
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': 'redis://{0}:{1}'.format(redis_hostname, redis_port),
            'KEY_PREFIX': 'default',
            'OPTIONS': {
                'DB': 0,
                'PARSER_CLASS': 'redis.connection.HiredisParser',
                'CONNECTION_POOL_CLASS': 'redis.BlockingConnectionPool',
                'CONNECTION_POOL_CLASS_KWARGS': {
                    'max_connections': 50,
                    'timeout': 20,
                },
                # 'MAX_CONNECTIONS': 1000,
                'PICKLE_VERSION': -1,  # Latest
            }
        }
    }
    # http://www.revsys.com/12days/caching-django-sessions/
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"

    # TODO: Enable if needed
    # Must be the first
    #MIDDLEWARE = ['django.middleware.cache.UpdateCacheMiddleware',] + MIDDLEWARE
    # This must be last
    #MIDDLEWARE = MIDDLEWARE + ['django.middleware.cache.FetchFromCacheMiddleware',]
    # pprint.pprint(CACHES)
elif env('CACHE_URL', None):
    CACHES = {
        'default': env.cache()
    }
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"

# Internationalization
# https://docs.djangoproject.com/en/dev/topics/i18n/

LANGUAGE_CODE = 'en-us'

USE_I18N = True

USE_L10N = True

USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/dev/howto/static-files/

ROOT_DIR = environ.Path(__file__) - 4
STATIC_ROOT = str(ROOT_DIR.path('staticfiles'))
STATICFILES_DIRS = []

STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
)


# Crispy Form Theme - Bootstrap 3
CRISPY_TEMPLATE_PACK = 'bootstrap3'

# For Bootstrap 3, change error alert to 'danger'
MESSAGE_TAGS = {
    messages.ERROR: 'danger'
}

# Authentication Settings
AUTH_USER_MODEL = 'authentication.Account'

# Recaptcha https://www.google.com/recaptcha/admin
# https://github.com/praekelt/django-recaptcha
RECAPTCHA_PUBLIC_KEY = get_secret('RECAPTCHA_SITE_KEY')
RECAPTCHA_PRIVATE_KEY = get_secret('RECAPTCHA_SECRET_KEY')
NOCAPTCHA = True
RECAPTCHA_USE_SSL = True

# https://github.com/ottoyiu/django-cors-headers/
CORS_ALLOW_CREDENTIALS = True
CORS_ORIGIN_ALLOW_ALL = True
CORS_URLS_REGEX = r'^/api.*$'
CORS_ORIGIN_WHITELIST = (
    'https://archsys.io',
    'https://iotile.cloud',
    'https://cdn.iotile.cloud'
)

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]
if not PRODUCTION:
    CORS_ORIGIN_WHITELIST += (
        'http://localhost:3002',
        'http://localhost:8000',
    )

CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True

# http://www.django-rest-framework.org/
REST_FRAMEWORK = {
    # Use hyperlinked styles by default.
    # Only used if the `serializer_class` attribute is not set on a view.
    'DEFAULT_MODEL_SERIALIZER_CLASS':
        'rest_framework.serializers.HyperlinkedModelSerializer',

    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    'DEFAULT_PERMISSION_CLASSES': (
        # 'rest_framework.permissions.IsAuthenticated', TODO: Should change to this
        'rest_framework.permissions.AllowAny',
    ),

    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_jwt.authentication.JSONWebTokenAuthentication',
        'apps.deviceauth.authentication.DeviceTokenAuthentication',
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),

    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
        'apps.utils.rest.renderers.BrowsableAPIRendererWithoutForms',
    ),

    'TEST_REQUEST_RENDERER_CLASSES': (
        'rest_framework.renderers.MultiPartRenderer',
        'rest_framework.renderers.JSONRenderer',
        'apps.streamer.msg_pack.MessagePackRenderer'
    ),

    'DEFAULT_FILTER_BACKENDS': ('django_filters.rest_framework.DjangoFilterBackend',),
    'DEFAULT_PAGINATION_CLASS': 'apps.utils.rest.pagination.StandardResultsSetPagination',

    # 'DATETIME_FORMAT': '%Y-%m-%dT%H:%M:%SZ'
    'DATETIME_INPUT_FORMATS': ['iso-8601', '%Y-%m-%dT%H:%M:%SZ']
}

JWT_AUTH = {

    'JWT_SECRET_KEY': SECRET_KEY,
    'JWT_ALGORITHM': 'HS256',
    'JWT_VERIFY': True,
    'JWT_VERIFY_EXPIRATION': True,
    'JWT_EXPIRATION_DELTA': datetime.timedelta(days=7),
    # 'JWT_PAYLOAD_GET_USERNAME_HANDLER': 'apps.authentication.models.get_username_field',
    # 'JWT_LEEWAY': 0,
    # 'JWT_AUDIENCE': None,
    # 'JWT_ISSUER': None,

    'JWT_ALLOW_REFRESH': True,
    'JWT_REFRESH_EXPIRATION_DELTA': datetime.timedelta(days=180),

    'JWT_AUTH_HEADER_PREFIX': 'JWT',
}

# auth and allauth settings
AUTHENTICATION_BACKENDS = (
    # Needed to login by username in Django admin, regardless of `allauth`
    "django.contrib.auth.backends.ModelBackend",
    # `allauth` specific authentication methods, such as login by e-mail
    "allauth.account.auth_backends.AuthenticationBackend"
)

LOGIN_REDIRECT_URL = '/'
LOGIN_URL = '/account/login/'
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
#SOCIALACCOUNT_EMAIL_REQUIRED = False
'''
SOCIALACCOUNT_PROVIDERS = {
    'facebook': {
        'SCOPE': ['email', 'public_profile'],
        #'AUTH_PARAMS': {'auth_type': 'reauthenticate'},
        'METHOD': 'oauth2',
        'VERSION': 'v2.4',
        'FIELDS': [
            'id',
            'email',
            'name',
            'first_name',
            'last_name',
            'verified',
            'locale',
            'timezone',
            'link',
        ],
    },
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': { 'access_type': 'online' }
    }
}
'''
ACCOUNT_USER_MODEL_USERNAME_FIELD = 'username'
ACCOUNT_USER_MODEL_EMAIL_FIELD = 'email'
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USERNAME_REQUIRED = True
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'

ACCOUNT_FORMS = {
    'login': 'apps.authentication.forms.AllauthLoginForm',
    'signup': 'apps.authentication.forms.AllauthSignupForm',
    'reset_password': 'apps.authentication.forms.AllauthResetPasswordForm',
    'reset_password_from_key': 'apps.authentication.forms.AllauthResetPasswordKeyForm',
}

ACCOUNT_ADAPTER = 'apps.invitation.adapter.InvitationAdapter'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

if PRODUCTION and not DOCKER:
    # For production, hard code to file created by .ebextensions
    LOG_FILEPATH = '/opt/python/log/my.log'
else:
    LOG_FILEPATH = os.path.join(str(LOG_FILE), 'server.log')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] %(message)s",
            'datefmt': "%d/%b/%Y %H:%M:%S"
        },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'filters': {
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'stderr': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'stream': sys.stderr
        },
        'default': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_FILEPATH,
            'maxBytes': 1024 * 1024 * 5,  # 5MB
            'backupCount': 5,
            'formatter': 'verbose'
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
        },
    },
    'loggers': {
        'django.security.DisallowedHost': {
            'handlers': ['mail_admins'],
            'level': 'CRITICAL',
            'propagate': False,
        },
        '': {
            'handlers': ['default', 'console'],
            'level': 'INFO',
            'propagate': True
        },
        'django': {
            'handlers': ['console'],
            'propagate': True,
        },
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'boto3': {
            'handlers': ['default', 'console'],
            'level': 'ERROR'
        },
        'botocore': {
            'handlers': ['default', 'console'],
            'level': 'ERROR'
        },
        'request': {
            'handlers': ['default', 'console'],
            'level': 'WARNING'
        },
        'health-check': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': True,
        },
    }
}

if env.bool('SENTRY_ENABLED', False):
    """Enable Sentry Error Logging"""

    INSTALLED_APPS += ('raven.contrib.django.raven_compat', )

    RAVEN_CONFIG = {
        'dsn': get_secret('SENTRY_DSN'),
        'release': '1.0',
    }

    LOGGING['handlers']['sentry'] = {
        'level': 'ERROR',
        'class': ('raven.contrib.django.raven_compat.handlers.SentryHandler'),
    }

    # Exception Handling
    LOGGING['loggers']['django.request']['handlers'].append('sentry')
    # logger.error()
    LOGGING['loggers']['']['handlers'].append('sentry')

if DOCKER and not PRODUCTION:
    print('PRODUCTION={}'.format(PRODUCTION))
    AWS_ACCESS_KEY_ID = env.str('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = env.str('AWS_SECRET_ACCESS_KEY')

    # BOTO may need an actual Env Variable, so set it
    os.environ['AWS_ACCESS_KEY_ID'] = AWS_ACCESS_KEY_ID
    os.environ['AWS_SECRET_ACCESS_KEY'] = AWS_SECRET_ACCESS_KEY

TEST_RUNNER = 'config.runner.AppsTestSuiteRunner'

# EMAIL
# ------------------------------------------------------------------------------
DEFAULT_FROM_EMAIL = env('DJANGO_DEFAULT_FROM_EMAIL', default='IOTile Cloud By Arch <noreply@notify.iotile.cloud>')
SERVER_EMAIL = 'IOTile Cloud By Arch <noreply@notify.iotile.cloud>'
EMAIL_SUBJECT_PREFIX = '[IOTile Cloud] '

# S3 Streamer Dropbox (New Scheme)
STREAMER_REPORT_DROPBOX_BUCKET_NAME = 'iotile-streamer-dropbox'
STREAMER_REPORT_DROPBOX_ENDPOINT = 'https://{}.s3.amazonaws.com/'.format(STREAMER_REPORT_DROPBOX_BUCKET_NAME)
STREAMER_REPORT_DROPBOX_KEY_FORMAT = '{stage}/{{username}}/{{date}}'.format(stage=SERVER_TYPE)
STREAMER_REPORT_DROPBOX_KEY_DATETIME_FORMAT_V2 = '%Y/%m/%d/%H'
STREAMER_REPORT_DROPBOX_KEY_FORMAT_V2 = '{stage}/{{streamer}}/{{path}}/{{uuid}}{{ext}}'.format(stage=SERVER_TYPE)
STREAMER_REPORT_DROPBOX_PUBLIC_KEY = get_secret('STREAMER_REPORT_DROPBOX_PUBLIC_KEY')
STREAMER_REPORT_DROPBOX_PRIVATE_KEY = get_secret('STREAMER_REPORT_DROPBOX_PRIVATE_KEY')
STREAMER_REPORT_DROPBOX_MAX_SIZE = 1024000  # 1M

S3IMAGE_BUCKET_NAME = 'iotile-cloud-media'
S3IMAGE_ENDPOINT = 'https://%s.s3.amazonaws.com/' % S3IMAGE_BUCKET_NAME
S3IMAGE_CDN = 'https://media.iotile.cloud'
S3IMAGE_INCOMING_KEYPATH = '{stage}/incoming'.format(stage=SERVER_TYPE)
S3IMAGE_KEY_FORMAT = '{domain}/{stage}/images/{{uuid}}/{{type}}.jpg'.format(
    domain=S3IMAGE_CDN, stage=SERVER_TYPE
)
S3IMAGE_PUBLIC_KEY = get_secret('S3IMAGE_PUBLIC_KEY')
S3IMAGE_PRIVATE_KEY = get_secret('S3IMAGE_PRIVATE_KEY')
S3IMAGE_MAX_SIZE = 4096000  # 4M

# S3 Files
# --------
S3FILE_BUCKET_NAME = S3IMAGE_BUCKET_NAME
S3FILE_ENDPOINT = 'https://%s.s3.amazonaws.com/' % S3FILE_BUCKET_NAME
S3FILE_CDN = 'https://media.iotile.cloud'
S3FILE_INCOMING_KEYPATH = '{stage}/s3file'.format(stage=SERVER_TYPE)
S3FILE_KEY_FORMAT = '{stage}/s3file/{{relative_key}}'.format(stage=SERVER_TYPE)
S3FILE_URL_FORMAT = '{0}{{key}}'.format(S3FILE_ENDPOINT)
S3FILE_PUBLIC_KEY = S3IMAGE_PUBLIC_KEY
S3FILE_PRIVATE_KEY = S3IMAGE_PRIVATE_KEY
S3FILE_MAX_SIZE = 4096000  # 4M

# Generated User Report S3 File info
# ----------------------------------
REPORTS_S3FILE_BUCKET_NAME = 'iotile-cloud-reports'
REPORTS_S3FILE_KEY_FORMAT = '{stage}/shared/{{org}}/{{uuid}}/{{base}}'.format(stage=SERVER_TYPE)

# S3 Streamer Reports
STREAMER_S3_BUCKET_NAME = 'iotile-cloud-streamers'
STREAMER_S3_KEY_FORMAT = '{stage}/streamer/{{slug}}/{{uuid}}.bin'.format(stage=SERVER_TYPE)

# S3 StreamEventData
#   Slug: Represents Stream Slug
#   id: ID of StreamEventData record
#   ext: File extension (e.g. json)
STREAM_EVENT_DATA_BUCKET_NAME = 'iotile-cloud-stream-event-data'
STREAM_EVENT_DATA_S3_KEY_FORMAT_V1 = '{stage}/{{slug}}/{{id}}.{{ext}}'.format(stage=SERVER_TYPE)
STREAM_EVENT_DATA_S3_KEY_DATETIME_FORMAT_V2 = '%Y/%m/%d/%H'
STREAM_EVENT_DATA_S3_KEY_FORMAT_V2 = '{stage}/{{path}}/{{id}}.{{ext}}'.format(stage=SERVER_TYPE)

# SNS Topics:
# -----------
# SNS_STREAM_WORKER is used to send messages to the back end stream-data-worker Lambda Functions
SNS_STREAM_WORKER = 'arn:aws:sns:us-east-1:xxxxxxxxxxxxxx:stream-data-worker-{stage}'.format(stage=SERVER_TYPE)
SNS_STAFF_NOTIFICATION = 'arn:aws:sns:us-east-1:xxxxxxxxxxxxxx:StaffNotification'
# Following SNS is used to publish to Arch's iotile-cloud Slack Channel
# Only used for publishing information that will be useful to everybody
SNS_ARCH_SLACK_NOTIFICATION = 'arn:aws:sns:us-east-1:xxxxxxxxxxxxxx:arch-slack-notifications-{stage}'.format(stage=SERVER_TYPE)
# SNS channel to delete record on s3
SNS_DELETE_S3 = 'arn:aws:sns:us-east-1:xxxxxxxxxxxxxx:iotile--delete-s3--{stage}'.format(stage=SERVER_TYPE)
# SNS channel to trigger processing of .SXd files
SNS_UPLOAD_SXD = 'arn:aws:sns:us-east-1:xxxxxxxxxxxxxx:iotile--upload-sxd--{stage}'.format(stage=SERVER_TYPE)

# Kinesis Firehose:
# -----------------
FIREHOSE_STREAM_NAME = 'stream-delivery'
USE_FIREHOSE = False

# DynamoDb
# --------
DYNAMODB_WORKERLOG_TABLE_NAME = 'iotile-worker-logs-{}'.format(SERVER_TYPE)
DYNAMODB_FILTER_LOG_TABLE_NAME = 'iotile-filter-log-{}'.format(SERVER_TYPE)
USE_DYNAMODB_WORKERLOG_DB = False
USE_DYNAMODB_FILTERLOG_DB = False

# SQS worker
SQS_WORKER_QUEUE_NAME = 'iotile-worker-{0}'.format(os.environ['SERVER_TYPE'])
SQS_ANALYTICS_QUEUE_NAME = 'iotile-report-{0}'.format(os.environ['SERVER_TYPE'])


# Google API Keys
# ---------------
GOOGLE_API_KEY = get_secret('GOOGLE_API_KEY')

USE_POSTGRES = DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql'

AWS_ELASTICSEARCH_HOST = env('AWS_ELASTICSEARCH_HOST', default=None)
if AWS_ELASTICSEARCH_HOST:
    import boto3
    from elasticsearch import RequestsHttpConnection
    from requests_aws4auth import AWS4Auth

    awsauth = AWS4Auth(
        get_secret('SEARCH_ACCESS_KEY_ID'),
        get_secret('SEARCH_SECRET_ACCESS_KEY'),
        AWS_REGION,
        'es'
    )

    ELASTICSEARCH_DSL = {
        'default': {
            'hosts': [{'host': AWS_ELASTICSEARCH_HOST, 'port': 443}],
            'http_auth': awsauth,
            'use_ssl': True,
            'verify_certs': True,
            'connection_class': RequestsHttpConnection
        }
    }
else:
    SEARCH_URL = env('SEARCH_URL', default=None)
    if SEARCH_URL:
        ELASTICSEARCH_DSL = {
            'default': {
                'hosts': SEARCH_URL
            },
        }
    else:
        ELASTICSEARCH_DSL = {
            'default': {
                'hosts': 'localhost:9200'
            },
        }


ENABLE_TWILIO = True
if ENABLE_TWILIO:
    TWILIO_AUTH_TOKEN = get_secret('TWILIO_AUTH_TOKEN')
    TWILIO_ACCOUNT_SID = get_secret('TWILIO_ACCOUNT_SID')
    TWILIO_FROM_NUMBER = env.str('TWILIO_FROM_NUMBER')

# drf-yasg
GENERATE_API_DOCS = True

SWAGGER_SETTINGS = {
    # 'DEFAULT_API_URL': '{}/api/v1/'.format(DOMAIN_BASE_URL),
    # 'DEFAULT_INFO': 'config.urls.swagger_info',
    'SECURITY_DEFINITIONS': {
        'JWT': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header'
        }
    },
}

# Note Bokeh_SECRET_KEY must also be used/set when starting up Bokeh daemon
# Obtain your own key by typing "bokeh secret" in a terminal
# the key goes below, and in the bokehserver.service file
os.environ["BOKEH_SECRET_KEY"] = "kitjOI83DgklnTuUykyHYABBCaV8oItJTZTQqVBav97G"
os.environ["BOKEH_SIGN_SESSIONS"] = "True"

# Data Manager: should be the import path to the class
DATA_MANAGER = 'apps.utils.data_helpers.manager.django_managers.streamdata_manager.DjangoStreamDataManager'

# OEE Caching worker
# Set this to True to push the OEE Caching tasks into SQS to be processed by other workers
# Set this to False to make all the Caching operations executed by only one worker
QUEUE_CACHING_TASKS = False

# Line metrics caching
# If this is set to False (which is default), the worker that cache the line metrics will shoot a SNS notification
# with debug information each time it is called.

METRICS_CACHING_DISABLE_DEBUG_NOTIF = env("METRICS_CACHING_DISABLE_DEBUG_NOTIF")
