from .base import *             # NOQA
import sys
import logging.config

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False
TEMPLATES[0]['OPTIONS'].update({'debug': DEBUG})
TESTING = True

TIME_ZONE = 'UTC'

STATIC_ROOT = str(ROOT_DIR.path('staticfiles'))
STATIC_URL = '/staticfiles/'
FAVICON_PATH = STATIC_URL + 'dist/webapp/app/extras/favicon.ico'
STATICFILES_DIRS = (
    ('dist', os.path.join(STATIC_ROOT, 'dist')),
)

LOGGING['loggers']['']['level'] = 'ERROR'

# Remove overhead to speed up tests
# See http://nemesisdesign.net/blog/coding/how-to-speed-up-tests-django-postgresql/
MIDDLEWARE = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.utils.timezoneMiddleware.TimezoneMiddleware',
]
# No need for fancy passports for testing. Make it fast instead
PASSWORD_HASHERS = (
    'django.contrib.auth.hashers.MD5PasswordHasher',
)

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
#SESSION_ENGINE = "django.contrib.sessions.backends.cache"

# Turn off debug while imported by Celery with a workaround
# See http://stackoverflow.com/a/4806384
if "celery" in sys.argv[0]:
    DEBUG = False

# Debug Toolbar (http://django-debug-toolbar.readthedocs.org/)
# By default (for development), show emails to console in DEBUG mode
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
#EMAIL_BACKEND = 'django_ses.SESBackend'

CORS_ORIGIN_WHITELIST += ('http://localhost:3000',)

# Kinesis Firehose:
# -----------------
USE_FIREHOSE = False
USE_DYNAMODB_WORKERLOG_DB = False
USE_DYNAMODB_FILTERLOG_DB = False

"""
class DisableMigrations(object):

    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None

if 'migrate' not in sys.argv:
    print('=================================')
    print('In TEST Mode - Disable Migrations')
    print('=================================')

    MIGRATION_MODULES = DisableMigrations()
"""

# SNS notifications are disabled for test
ENABLE_STAFF_SNS_NOTIFICATIONS = False
