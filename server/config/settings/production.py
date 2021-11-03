# In production set the environment variable like this:
#    DJANGO_SETTINGS_MODULE=config.settings.production
import socket
import requests
from requests.exceptions import ConnectionError
from django.core.exceptions import ImproperlyConfigured

from .base import *

# For security and performance reasons, DEBUG is turned off
DEBUG = False
TEMPLATES[0]['OPTIONS'].update({'debug': False})

TIME_ZONE = 'UTC'

print('**********************************')
print('**********************************')
print('INFO: Production Settings')
print('INFO: Debug = {0}'.format(DEBUG))
print('**********************************')
print('**********************************')

enable_security = True
if enable_security:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # CSRF_USE_SESSIONS = True
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = True
    CSRF_COOKIE_SAMESITE = 'Strict'

    SECURE_HSTS_SECONDS = 15768000  # 6 months
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

    # Instructs the browser to send the full URL as the referrer
    # for same-origin links, and only the origin for cross-origin links.
    SECURE_REFERRER_POLICY = 'origin-when-cross-origin'

    X_FRAME_OPTIONS = 'DENY'

    '''
    The following comes from:
    http://security.stackexchange.com/questions/8964/trying-to-make-a-django-based-site-use-https-only-not-sure-if-its-secure/8970#comment80472_8970
    '''
    os.environ['HTTPS'] = "on"
    # SECURE_SSL_REDIRECT must not be set as we are using NGINX which talks to Django with http
    SECURE_SSL_REDIRECT = False

    local_ip = str(socket.gethostbyname(socket.gethostname()))
    print('hostname: ' + socket.gethostname())
    print('hostbyname: ' + local_ip)

    # Must mention ALLOWED_HOSTS in production!
    ALLOWED_HOSTS = [local_ip,
                     'iotile.cloud',
                     '*.iotile.cloud',
                     'iotile-cloud-web1.us-east-1.elasticbeanstalk.com']

    # ALLOWED_HOSTS
    url = "http://169.254.169.254/latest/meta-data/public-ipv4"
    try:
        r = requests.get(url)
        instance_ip = r.text
        ALLOWED_HOSTS.append(instance_ip)
    except ConnectionError:
        error_msg = "You can only run production settings on an AWS EC2 instance"
        raise ImproperlyConfigured(error_msg)
    # END ALLOWED_HOSTS

    # Settings for django-feature-policy
    FEATURE_POLICY = {
        'geolocation': [
            'self',
            'https://app.iotile.cloud',
            'https://app-stage.iotile.cloud',
            'https://factory.iotile.cloud'
        ]
    }

    print(str(ALLOWED_HOSTS))
else:
    ALLOWED_HOSTS = ['*', ]
    print('**********************************')
    print('**********************************')
    print('WARNING: Disable security features')
    print('**********************************')
    print('**********************************')


# Cache the templates in memory for speed-up
loaders = [
    ('django.template.loaders.cached.Loader', [
        'django.template.loaders.filesystem.Loader',
        'django.template.loaders.app_directories.Loader',
    ]),
]

TEMPLATES[0]['OPTIONS'].update({"loaders": loaders})
TEMPLATES[0].update({"APP_DIRS": False})

# Define STATIC_ROOT for the collectstatic command
# Setup CloudFront
AWS_S3_URL_PROTOCOL = 'https'
# Enable one AWS_S3_CUSTOM_DOMAIN to use cloudfront
AWS_S3_CUSTOM_DOMAIN = 'cdn.iotile.cloud'
STATIC_URL = AWS_S3_URL_PROTOCOL + '://' + AWS_S3_CUSTOM_DOMAIN + '/static/'
FAVICON_PATH = AWS_S3_URL_PROTOCOL + '://' + AWS_S3_CUSTOM_DOMAIN + '/static/dist/webapp/app/extras/favicon.ico'

print('AWS_S3_CUSTOM_DOMAIN = {0}, STATIC_URL={1}'.format(AWS_S3_CUSTOM_DOMAIN, STATIC_URL))

# Email Config
# ------------
EMAIL_BACKEND = 'django_ses.SESBackend'
print('EMAIL_BACKEND = {0}'.format(EMAIL_BACKEND))

# Kinesis Firehose:
# -----------------
USE_FIREHOSE = True

# Worker Setup
# --------------
USE_WORKER = True
USE_DYNAMODB_WORKERLOG_DB = True

# Stream Filter
USE_DYNAMODB_FILTERLOG_DB = True

# SNS notifications are enabled for production
ENABLE_STAFF_SNS_NOTIFICATIONS = True
