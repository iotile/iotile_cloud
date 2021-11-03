import json
from django import forms
from django.forms import ModelForm
from django.contrib.auth import get_user_model
from datetime import datetime
from django.db.models import Q
from django.core.validators import validate_email
from django.contrib.postgres.forms import SimpleArrayField
from django.core.exceptions import ValidationError

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, ButtonHolder, HTML, Div
from crispy_forms.bootstrap import FieldWithButtons

from apps.org.models import Org
from apps.project.models import Project
from apps.physicaldevice.models import Device
from apps.physicaldevice.claim_utils import DEFAULT_IOTILE_DEVICE_NAME_FORMAT
from apps.physicaldevice.state import DEVICE_STATE_CHOICES
from apps.devicetemplate.models import DeviceTemplate
from apps.sensorgraph.models import SensorGraph
from apps.stream.models import StreamId

user_model = get_user_model()


class GetDeviceForm(forms.Form):
    device_id = forms.CharField(label='Global Device ID', max_length=38, required=True)

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            FieldWithButtons('device_id', Submit('search', 'GO!', css_class='btn btn-success btn-block', )),
            HTML('<p> *Use regular integers (e.g. "10") or hex format (e.g. "0xa")</p>'),
            HTML('<br>')
        )

        super(GetDeviceForm, self).__init__(*args, **kwargs)

    def _parse_int(self, value):
        try:
            result = int(value)
        except ValueError:
            try:
                result = int(value, 16)
            except ValueError:
                raise forms.ValidationError('Only <int> (10) or <hex> (0xa) format accepted')
        return result

    def clean_device_id(self):
        # Check that device exists
        raw_id = self.cleaned_data.get('device_id')
        device_id = self._parse_int(raw_id)
        try:
            device = Device.objects.get(pk=device_id)
        except Device.DoesNotExist:
            raise forms.ValidationError('Device not found')

        return device
