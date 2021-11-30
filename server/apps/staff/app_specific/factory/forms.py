
from django import forms
from django.contrib.auth import get_user_model
from django.forms import ModelForm
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Layout, Submit

from apps.configattribute.models import ConfigAttribute, get_or_create_config_name
from apps.devicetemplate.models import DeviceTemplate
from apps.org.models import Org
from apps.project.models import Project
from apps.sensorgraph.models import SensorGraph

user_model = get_user_model()
STREAMER_REPORT_FORWARDER_CONFIG_NAME = ':classic:streamer:forwarder:config'


class NewStreamerForwarderConfigForm(ModelForm):
    """Form to configure Streamer Report Forwarder
    Will create a ConfigAttribute for:
        STREAMER_REPORT_FORWARDER_CONFIG_NAME
    """

    org = forms.ModelChoiceField(
        label=_('Org'), queryset=Org.objects.all(),
        help_text=_('Streamer Reports from this Org will be forwrded')
    )
    url = forms.CharField(
        label='API Domain', max_length=60, required=True,
        help_text=_('Forwarging Cloud Domain URL (e.g. https://arch.archfx.io)')
    )
    key = forms.CharField(
        label=_('API Key'), max_length=45, required=True,
        help_text=_('Machine to Machine API Key')
    )
    user = None

    class Meta:
        model = ConfigAttribute
        fields = []

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        self.helper = FormHelper()
        self.helper.form_method = 'post'

        self.helper.layout = Layout(
            Div(
                Div('org', css_class='col-sm-6, col-xs-6'),
                Div('url', css_class='col-sm-6, col-xs-6'),
                css_class='row'
            ),
            'key',
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', _('Configure new Streamer Forwarder'), css_class='btn btn-block btn-success submit'))

        super(NewStreamerForwarderConfigForm, self).__init__(*args, **kwargs)

    def clean_org(self):
        """Make sure we don't already have a config for this same Org"""
        org = self.cleaned_data.get('org')
        name = get_or_create_config_name(STREAMER_REPORT_FORWARDER_CONFIG_NAME)
        if ConfigAttribute.objects.filter(target=org.obj_target_slug, name=name).exists():
            raise forms.ValidationError('Existing Config already exists for {}'.format(org.name))
        return org

    def save(self, commit=True):
        """Manually create the required ConfgiAttribute"""
        org = self.clean_org()
        config = ConfigAttribute.objects.get_or_create_attribute(
            target=org,
            name=STREAMER_REPORT_FORWARDER_CONFIG_NAME,
            data={
                "enabled": True,
                "api_url": self.cleaned_data.get('url'),
                "api_key": self.cleaned_data.get('key'),
            },
            updated_by=self.user
        )

        return config


class ArchFxDeviceBatchForm(forms.Form):
    template = forms.ModelChoiceField(
        label='Device Template',
        queryset=DeviceTemplate.objects.all().order_by('external_sku'),
        required=True
    )
    sg = forms.ModelChoiceField(
        label='Sensor Graph',
        queryset=SensorGraph.objects.filter(active=True).order_by('name'),
        required=True
    )
    org = forms.ModelChoiceField(
        label='Assigned Org',
        queryset=Org.objects.all().order_by('name'),
        required=True
    )
    name_format = forms.CharField(label='Name', max_length=100, required=True,)
    num_devices = forms.IntegerField(label='Number of Devices', min_value=1, required=True)

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<br>'),
            Div(
                Div('template', css_class='col-xs-6'),
                Div('sg', css_class='col-xs-6'),
                css_class='row'
            ),
            'org',
            Div(
                Div(Field('name_format', placeholder='ArchFX Device'), css_class='col-xs-8'),
                Div('num_devices', css_class='col-xs-4'),
                css_class='row'
            ),
            HTML('<p>{id} most be included somewhere in the string. It will be replaced by the device ID</p>'),
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Create', css_class='btn btn-default submit'))

        super(ArchFxDeviceBatchForm, self).__init__(*args, **kwargs)
        self.initial['name_format'] = 'ArchFX Device ({id})'
        self.initial['num_devices'] = 1

    def clean_name_format(self):
        # Check that username is not used already
        name_format = self.cleaned_data.get('name_format')
        if '{id}' not in name_format:
            raise forms.ValidationError('You must use {id} somewhere in the name')
        return name_format
