import importlib

from django.conf import settings

module, klass = settings.DATA_MANAGER.rsplit('.', maxsplit=1)

# The exposed DataManager class just inherits from the settings class
DataManager = type(
    'DataManager',
    (getattr(importlib.import_module(module), klass), ),
    {}
)
