from .base import *             # NOQA
import sys
import logging.config

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
TEMPLATES[0]['OPTIONS'].update({'debug': True})

TIME_ZONE = 'UTC'

STATIC_ROOT = str(ROOT_DIR.path('staticfiles'))
STATIC_URL = '/staticfiles/'
FAVICON_PATH = STATIC_URL + 'dist/webapp/app/extras/favicon.ico'
STATICFILES_DIRS = (
    ('dist', os.path.join(STATIC_ROOT, 'dist')),
)

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://localhost:6379',
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
SESSION_ENGINE = "django.contrib.sessions.backends.cache"

# Turn off debug while imported by Celery with a workaround
# See http://stackoverflow.com/a/4806384
if "celery" in sys.argv[0]:
    DEBUG = False

# Debug Toolbar (http://django-debug-toolbar.readthedocs.org/)
INSTALLED_APPS += ('debug_toolbar',)
DEBUG_TOOLBAR_PATCH_SETTINGS = False
MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware', ]
INTERNAL_IPS = ('127.0.0.1', '192.168.99.100',)
DEBUG_TOOLBAR_PANELS = [
    'debug_toolbar.panels.versions.VersionsPanel',
    'debug_toolbar.panels.timer.TimerPanel',
    'debug_toolbar.panels.settings.SettingsPanel',
    'debug_toolbar.panels.headers.HeadersPanel',
    'debug_toolbar.panels.request.RequestPanel',
    'debug_toolbar.panels.sql.SQLPanel',
    'debug_toolbar.panels.cache.CachePanel',
    # 'debug_toolbar.panels.staticfiles.StaticFilesPanel',
    'debug_toolbar.panels.templates.TemplatesPanel',
    'debug_toolbar.panels.signals.SignalsPanel',
    'debug_toolbar.panels.logging.LoggingPanel',
    'debug_toolbar.panels.redirects.RedirectsPanel',
]
DEBUG_TOOLBAR_CONFIG = {
    'JQUERY_URL': '',
}

# By default (for development), show emails to console in DEBUG mode
#EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
#EMAIL_BACKEND = 'django_ses.SESBackend'
print('EMAIL_BACKEND = {0}'.format(EMAIL_BACKEND))

CORS_ORIGIN_WHITELIST += ('http://localhost:3000',)

# Kinesis Firehose:
# -----------------
USE_FIREHOSE = False

# Dynamodb Usage
# --------------
USE_DYNAMODB_WORKERLOG_DB = True
USE_DYNAMODB_FILTERLOG_DB = True

USE_WORKER = False

# SNS notifications are disabled for development
ENABLE_STAFF_SNS_NOTIFICATIONS = False
