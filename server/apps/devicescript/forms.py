from django import forms
from django.forms import ModelForm
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Div, HTML

from .models import *


class DeviceScriptForm(ModelForm):

    class Meta:
        model = DeviceScript
        exclude = ['created_by', 'released_on', 'released', 'slug', 'gid', 'org', 'form']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<br>'),
            Div(
                Div('name', css_class='col-xs-12'),
                css_class='row'
            ),
            Div(
                Div('major_version', css_class='col-xs-4'),
                Div('minor_version', css_class='col-xs-4'),
                Div('patch_version', css_class='col-xs-4'),
                css_class='row'
            ),
            'notes',
            HTML('<h4>You will be able to upload a file and mark as released after creating record</h4>'),
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', _('Submit'), css_class='btn btn-default submit'))

        super(DeviceScriptForm, self).__init__(*args, **kwargs)


class DeviceScriptReleaseForm(ModelForm):

    class Meta:
        model = DeviceScript
        fields = ['released',]

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<br>'),
            HTML('<h3>Device Script: {{ object.slug }}</h3>'),
            HTML('<br>'),
            HTML('<hr>'),
            'released',
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', _('Submit'), css_class='btn btn-default submit'))

        super(DeviceScriptReleaseForm, self).__init__(*args, **kwargs)

