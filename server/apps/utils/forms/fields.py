import json

from django.forms import JSONField
from django.forms.fields import InvalidJSONInput


class FormattedJsonField(JSONField):
    def prepare_value(self, value):
        if isinstance(value, InvalidJSONInput):
            return value
        return json.dumps(value, indent=2)
