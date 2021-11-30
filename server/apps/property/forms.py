from django import forms
from django.forms import ModelForm

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Button, Div, Field, Layout, Submit

from .models import *


class GenericPropertyForm(ModelForm):

    class Meta:
        model = GenericProperty
        fields = ['name', 'str_value', 'type', 'is_system']

    def clean(self):
        cleaned_data = super(GenericPropertyForm, self).clean()
        type = cleaned_data.get("type")
        str_value = cleaned_data.get("str_value")
        name = cleaned_data.get("name")

        if GenericProperty.objects.filter(name=name, target=self.target_slug).exists():
            raise forms.ValidationError({'name': ['Property with name "{0}" already exists'.format(name)]})

        if type is not None and str_value is not None:
            if type == 'bool' and not((str_value == 'True') or (str_value == 'False')):
                raise forms.ValidationError({'str_value': ["Value must be either 'True' or 'False'"]})
            elif type == 'int':
                try:
                    int(str_value)
                except ValueError:
                    raise forms.ValidationError({'str_value': ["Value must be an Integer"]})

    def __init__(self, *args, **kwargs):
        self.target_slug = kwargs.pop('target_slug', None)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'name',
            Div(
                Div('type', css_class='col-sm-4 col-xs-8'),
                Div('str_value', css_class='col-sm-8 col-xs-12'),
                css_class='row'
            ),
            'is_system'
        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))

        super(GenericPropertyForm, self).__init__(*args, **kwargs)


class GenericPropertyDeleteConfirmForm(ModelForm):

    class Meta:
        model = GenericProperty
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Confirm', css_class='btn btn-danger submit'))
        self.helper.layout = Layout(
            HTML('<h2>Are you sure you want to delete property {{object.name}} ?</h2><br>')
        )
        super(GenericPropertyDeleteConfirmForm, self).__init__(*args, **kwargs)


class GenericPropertyOrgEnumForm(ModelForm):

    class Meta:
        model = GenericPropertyOrgEnum
        fields = ['value', 'template']

    def clean(self):
        cleaned_data = super(GenericPropertyOrgEnumForm, self).clean()
        value = cleaned_data.get('value')
        template = cleaned_data.get('template')

        if GenericPropertyOrgEnum.objects.filter(value=value, template=template).exists():
            raise forms.ValidationError({'value': ['value "{0}" already exists'.format(value)]})

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        template = kwargs.pop('template', None)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'value',
            'template'
        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))

        super(GenericPropertyOrgEnumForm, self).__init__(*args, **kwargs)
        if template:
            self.fields['template'].queryset = GenericPropertyOrgTemplate.objects.filter(org=org, id=template.id)
            self.fields['template'].initial = template
        else:
            self.fields['template'].queryset = GenericPropertyOrgTemplate.objects.filter(org=org)


class GenericPropertyOrgEnumDeleteConfirmForm(ModelForm):

    class Meta:
        model = GenericProperty
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Confirm', css_class='btn btn-danger submit'))
        self.helper.layout = Layout(
            HTML('<h2>Are you sure you want to delete "{{object.value}}"?</h2><br>')
        )
        super(GenericPropertyOrgEnumDeleteConfirmForm, self).__init__(*args, **kwargs)
