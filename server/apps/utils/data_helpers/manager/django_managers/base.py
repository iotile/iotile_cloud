import types
import uuid
from datetime import datetime

from iotile_cloud.utils.gid import *


class ClassMethodsOnly(type):
    def __new__(cls, name, bases, attrs):
        for attr_name, attr_value in attrs.items():
            if isinstance(attr_value, types.FunctionType):
                attrs[attr_name] = classmethod(attr_value)
        return super(ClassMethodsOnly, cls).__new__(cls, name, bases, attrs)


class DjangoBaseDataManager(metaclass=ClassMethodsOnly):
    """
    Base DataManager for Django ORM
    """

    ARGS = {
        'filter': {
            'legal_args': {
                'device_slug': {str, IOTileDeviceSlug},
                'device_slug__in': {list},
                'dirty_ts': {bool},
                'id__in': {list},
                'project_slug': {str, IOTileProjectSlug},
                'project_slug__in': {list},
                'stream_slug': {str, IOTileStreamSlug},
                'stream_slug__in': {list},
                'streamer_local_id': {int},
                'streamer_local_id__gt': {int},
                'streamer_local_id__gte': {int},
                'streamer_local_id__in': {list},
                'streamer_local_id__lt': {int},
                'streamer_local_id__lte': {int},
                'timestamp__gt': {str, datetime},
                'timestamp__gte': {str, datetime},
                'timestamp__lt': {str, datetime},
                'timestamp__lte': {str, datetime},
                'variable_slug': {str, IOTileVariableSlug},
                'variable_slug__contains': {str},
                'variable_slug__endswith': {str},
                'variable_slug__icontains': {str},
            },
            'legal_extra_args': {
                'data': {
                    'int_value': {int},
                    'int_value__in': {list},
                },
            },

        },
        'get': {
            'legal_args': {
                'device_slug': {str, IOTileDeviceSlug},
                'streamer_local_id': {int},
            },
            'legal_extra_args': {
                'event': {
                    'uuid': {str, uuid.UUID},
                },
            },
        },
        'build': {
            'legal_args': {
                'device_timestamp': {int},
                'status': {str},
                'stream_slug': {str, IOTileStreamSlug},
                'streamer_local_id': {int},
                'timestamp': {datetime},
            },
            'legal_extra_args': {
                'event': {
                    'extra_data': {dict},
                },
                'data': {
                    'type': {str},
                    'value': {float},
                    'int_value': {int}
                }
            },
        },
    }

    def get_model(cls, name):
        """
        Returns the model corresponding to the name
        Defines 'data' and 'event' models
        """
        raise NotImplementedError

    def _validate_arg_and_value(cls, operation, arg, value, extra=None):
        if extra is not None:
            assert extra in cls.ARGS[operation]['legal_extra_args'], 'Invalid extra args for model {}'.format(extra)
            assert arg in cls.ARGS[operation]['legal_extra_args'][extra], 'Invalid extra arg {}'.format(arg)
            assert type(value) in cls.ARGS[operation]['legal_extra_args'][extra][arg], 'Invalid type for extra arg {}: {}'.format(arg, type(value))
        else:
            assert arg in cls.ARGS[operation]['legal_args'], 'Invalid argument {}'.format(arg)
            assert type(value) in cls.ARGS[operation]['legal_args'][arg], 'Invalid type for argument {}: {}'.format(arg, type(value))

    def _validate_q(cls, model, operation, q, extras):
        res = {}
        # children are either (key, value) tuples or other Q objects
        for child in q.children:
            if type(child) is tuple:
                arg, value = child
                if arg in extras:
                    cls._validate_arg_and_value(operation, arg, value, extra=model)
                else:
                    cls._validate_arg_and_value(operation, arg, value)
            else:
                cls._validate_q(model, operation, child, extras)

    def _validate_kwargs(cls, model, operation, kwargs):
        """validate kwargs and transform the dict to add extras"""
        # get extras dict
        extras = kwargs.pop('extras', {})
        # validate regular arguments
        for arg, value in kwargs.items():
            cls._validate_arg_and_value(operation, arg, value)
        # validate extras and add arguments to kwargs
        for extra_arg, extra_value in extras.items():
            cls._validate_arg_and_value(operation, extra_arg, extra_value, extra=model)
            kwargs[extra_arg] = extra_value

    def all_qs(cls, model):
        return cls.get_model(model).objects.all()

    def none_qs(cls, model):
        return cls.get_model(model).objects.none()

    def count(cls, model):
        return cls.get_model(model).objects.count()

    def is_instance(cls, model, obj):
        return isinstance(obj, cls.get_model(model))

    def save(cls, model, obj, **kwargs):
        assert cls.is_instance(model, obj)
        return obj.save(**kwargs)

    def bulk_create(cls, model, payload):
        return cls.get_model(model).objects.bulk_create(payload)

    def send_to_firehose(cls, model, payload):
        raise NotImplementedError

    def build(cls, model, **kwargs):
        raise NotImplementedError

    def get(cls, model, **kwargs):
        raise NotImplementedError

    def filter_qs(cls, model, **kwargs):
        raise NotImplementedError

    def filter_qs_using_q(cls, model, q, extras=[]):
        raise NotImplementedError

    def df_filter_qs_using_q(cls, model, q, extras=[]):
        raise NotImplementedError
