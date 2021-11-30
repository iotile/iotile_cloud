from django import forms
from django.forms import ModelForm
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Layout, Submit

from .models import *


class DeviceFileForm(ModelForm):

    class Meta:
        model = DeviceFile
        exclude = ['created_by', 'created_on', 'slug', 'released_by', 'file']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<br>'),
            Div(
                Div('type', css_class='col-xs-6'),
                Div('tag', css_class='col-xs-6'),
                css_class='row'
            ),
            Div(
                Div('major_version', css_class='col-xs-6'),
                Div('minor_version', css_class='col-xs-6'),
                css_class='row'
            ),
            'released',
            'notes',
            HTML('<h4>You will be able to upload a file after creating record</h4>'),
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', _('Submit'), css_class='btn btn-default submit'))

        super(DeviceFileForm, self).__init__(*args, **kwargs)
