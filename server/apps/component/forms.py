from django import forms
from django.forms import ModelForm
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Layout, Submit

from apps.devicetemplate.models import DeviceTemplate

from .models import *


class ComponentForm(ModelForm):
    class Meta:
        model = Component
        exclude = ['slug', 'created_by',]

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<br>'),
            Div(
                Div('external_sku', css_class='col-xs-12'),
                css_class='row'
            ),
            Div(
                Div('internal_sku', css_class='col-xs-12 col-sm-8'),
                Div('type', css_class='col-xs-8 col-sm-4'),
                css_class='row'
            ),
            Div(
                Div('hw_name', css_class='col-xs-12 col-sm-8'),
                Div('hw_tag', css_class='col-xs-4 col-sm-4'),
                css_class='row'
            ),
            Div(
                Div('org', css_class='col-xs-12 col-sm-8'),
                css_class='row'
            ),
            Div(
                Div('major_version', css_class='col-xs-4'),
                Div('minor_version', css_class='col-xs-4'),
                Div('patch_version', css_class='col-xs-4'),
                css_class='row'
            ),
            'description',
            Div(
                Div('active', css_class='col-xs-4'),
                css_class='row'
            ),
        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success btn-block submit'))

        super(ComponentForm, self).__init__(*args, **kwargs)
        if self.instance.org_id:
            self.fields['org'].queryset = Org.objects.filter(id=self.instance.org_id)
        else:
            self.fields['org'].queryset = Org.objects.filter(is_vendor=True).order_by('name')

