from django.forms import ModelForm
from django import forms
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Div, HTML

from .models import *

class OrgTemplateForm(ModelForm):

    class Meta:
        model = OrgTemplate
        exclude = ['slug', 'created_by', ]

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Div(
                Div('name', css_class='col-sm-8'),
                css_class='row'
            ),
            'active',
            HTML('<br>'),
            Div(
                Div('major_version', css_class='col-xs-4'),
                Div('minor_version', css_class='col-xs-4'),
                Div('patch_version', css_class='col-xs-4'),
                css_class='row'
            ),
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-default submit'))

        super(OrgTemplateForm, self).__init__(*args, **kwargs)
        self.fields['org'].queryset = Org.objects.filter(is_vendor=True).all().order_by('name')

