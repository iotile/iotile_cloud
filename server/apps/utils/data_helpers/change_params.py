"""
This file defines the change_params decorator. Its role is to dynamically change parameters before
calling a function. For instance:

@change_params
def filter(**kwargs):
    return StreamTimeSeriesValue.objects.filter(**kwargs)

Calling filter(project_slug='p--0000-018d') is equivalent to calling filter(project_id=397)
"""
import re
from functools import wraps

from iotile_cloud.utils.gid import *


class ConvertParamBase:
    """
    Abtract class to convert a field
    Derived classes must implement convert_field
    """
    MULTIPLE_VALUES_LOOKUPS = {'in', 'range'}

    def __init__(self, param, value):
        self.param = param
        self.value = value
        self._create_field_and_lookups()

    def _create_field_and_lookups(self):
        """get field and lookups from parameter"""
        regex = r'^(?P<field>((?!__)\S)*)(?P<lookups>__[a-z_]*){0,1}$'
        parts = re.match(regex, self.param)
        if parts:
            self.field = parts.group('field')
            if parts.group('lookups') is not None:
                self.lookups = parts.group('lookups')
                self.lookups_set = set(self.lookups.split('__'))
            else:
                self.lookups = str()
                self.lookups_set = set()
        else:
            raise ValueError('param has a wrong format')

    def _convert_field_wrapper(self, value):
        """add the lookups to the results of self.convert_field"""
        results = self.convert_field(self.field, value)
        return {k + self.lookups: v for k, v in results.items()}

    def get_processed_parameters(self):
        """Main method: handles multiple or single values and calls convert_field for the conversion"""
        if self.MULTIPLE_VALUES_LOOKUPS & self.lookups_set:
            results = {}
            for value in self.value:
                for k, v in self._convert_field_wrapper(value).items():
                    results.setdefault(k, []).append(v)
            return {k: type(self.value)(v) for k, v in results.items()}
        else:
            return self._convert_field_wrapper(self.value)

    def convert_field(self, field, value):
        """This method must be implemented by the derived classes.

        Args:
            field (str): field which must be converted.
            value (object): value corresponding to the field: must be converted too.

        Returns:
            dict: maps new fields to new values.
        """
        raise NotImplementedError


class ConvertProjectSlug(ConvertParamBase):
    """Converts project_slug into project_id"""

    def convert_field(self, field, value):
        assert field == 'project_slug'
        project_id = IOTileProjectSlug(value).get_id() if value is not None else None
        return {'project_id': project_id}


class ConvertDeviceSlug(ConvertParamBase):
    """Converts device_slug into device_id and block_id"""

    def convert_field(self, field, value):
        assert field == 'device_slug'
        if not value:
            return {'device_id': None}
        # device_slug can represent a block
        if value[0] == 'b':
            device_id = IOTileBlockSlug(value).get_id()
            block_id = IOTileBlockSlug(value).get_block()
        else:
            device_id = IOTileDeviceSlug(value).get_id()
            block_id = None
        return {
            'device_id': device_id,
            'block_id': block_id,
        }


class ConvertVariableSlug(ConvertParamBase):
    """Converts variable_slug into variable_id and project_id"""

    def convert_field(self, field, value):
        assert field == 'variable_slug'
        if not value:
            return {'variable_id': None}
        variable_id = int(IOTileVariableSlug(value).formatted_local_id(), 16)
        # variable slug contains information about the project which mustn't be lost
        project_slug = 'p--{}'.format(value.split('--')[1])
        project_id = IOTileProjectSlug(project_slug).get_id()
        return {
            'variable_id': variable_id,
            'project_id': project_id,
        }


def identity(new_field):
    """Returns a class which maps new_field to the same value."""
    return type(
        'NewFieldSameValue_{}'.format(new_field),
        (ConvertParamBase, ),
        {
            'convert_field': lambda self, field, value: {new_field: value},
        }
    )


# This dict maps a parameter to a class implementing ConvertParamBase.convert_field
PARAMS_TO_CHANGE = {
    'project_slug': ConvertProjectSlug,
    'device_slug': ConvertDeviceSlug,
    'variable_slug': ConvertVariableSlug,
    'streamer_local_id': identity('device_seqid'),
    # None means the parameter will be ignored
    'dirty_ts': None,
    'int_value': identity('raw_value'),
}


def push(key, value, dictionary):
    """Push a key value pair into the dictionary after checking consistency"""
    if key in dictionary and dictionary[key] != value:
        # if there is an in or range lookup, then we can find consistency
        # just get the intersection of value and dictionary[key]
        if '__in' in key:
            dictionary[key] = type(value)((v for v in value if v in dictionary[key]))
        # consistent if the ranges can be merged
        elif '__range' in key:
            begin_new, end_new = value
            begin_old, end_old = dictionary[key]
            # must be in both ranges
            max_begin = max(begin_new, begin_old)
            min_end = min(end_new, end_old)
            if max_begin > min_end:
                raise ValueError('Inconsistent parameters are used')
            dictionary[key] = type(value)((max_begin, min_end))
        else:
            raise ValueError('Inconsistent parameters are used')
    # just push the key value pair if it isn't already in the dict
    else:
        dictionary[key] = value


def change_params(func):
    """
    Change the parameters before calling the function so that they match parameters
    for StreamTimeSeriesValue. For instance, project_slug='slug' is changed to
    project_id=id_of_slug('slug').
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        new_kwargs = {}
        for param, value in kwargs.items():
            for param_to_change, convert_class in PARAMS_TO_CHANGE.items():
                if param_to_change in param:
                    if convert_class is None:
                        break
                    converter = convert_class(param, value)
                    for k, v in converter.get_processed_parameters().items():
                        push(k, v, new_kwargs)
                    break
            else:
                push(param, value, new_kwargs)
        return func(*args, **new_kwargs)
    return wrapper
