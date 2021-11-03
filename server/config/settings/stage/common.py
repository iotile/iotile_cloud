import socket
from ..base import *             # NOQA
import sys
import logging.config

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
TEMPLATES[0]['OPTIONS'].update({'debug': True})

TIME_ZONE = 'UTC'

STATIC_URL = '/static/'
STATIC_ROOT = '/www/static/'
STATICFILES_DIRS = (
    ('dist', os.path.join(STATIC_ROOT, 'dist')),
)

LOGGING['loggers']['']['level'] = 'INFO'

local_ip = str(socket.gethostbyname(socket.gethostname()))
print('IP={}'.format(local_ip))

# Must mention ALLOWED_HOSTS in production!
ALLOWED_HOSTS = [local_ip, '192.168.0.13', '.corp.archsys.io', '*']
print(str(ALLOWED_HOSTS))

#ALLOWED_HOSTS = ['*', ]
# print('**********************************')
# print('**********************************')
#print('WARNING: Disable security features')
# print('**********************************')
# print('**********************************')

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

# Turn off debug while imported by Celery with a workaround
# See http://stackoverflow.com/a/4806384
if "celery" in sys.argv[0]:
    DEBUG = False

# Debug Toolbar (http://django-debug-toolbar.readthedocs.org/)
INSTALLED_APPS += ('debug_toolbar',)
DEBUG_TOOLBAR_PATCH_SETTINGS = False
MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware', ]
INTERNAL_IPS = ('127.0.0.1', '192.168.99.100', '192.168.0.13')
DEBUG_TOOLBAR_PANELS = [
    'debug_toolbar.panels.versions.VersionsPanel',
    'debug_toolbar.panels.timer.TimerPanel',
    'debug_toolbar.panels.settings.SettingsPanel',
    'debug_toolbar.panels.headers.HeadersPanel',
    'debug_toolbar.panels.request.RequestPanel',
    'debug_toolbar.panels.sql.SQLPanel',
    # 'debug_toolbar.panels.staticfiles.StaticFilesPanel',
    'debug_toolbar.panels.templates.TemplatesPanel',
    'debug_toolbar.panels.signals.SignalsPanel',
    'debug_toolbar.panels.logging.LoggingPanel',
    'debug_toolbar.panels.redirects.RedirectsPanel',
]

# Email Config
# ------------
EMAIL_BACKEND = 'django_ses.SESBackend'

USE_DYNAMODB_DEVICE_DB = True
USE_DYNAMODB_WORKERLOG_DB = True

# SNS notifications are disabled for production
ENABLE_STAFF_SNS_NOTIFICATIONS = False
