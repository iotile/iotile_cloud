import logging

from django import forms as forms
from django.contrib import messages
from django.db.models import Q
from django.forms import ModelForm
from django.template.defaultfilters import slugify

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Button, Div, Field, Layout, Submit

from .models import *

logger = logging.getLogger(__name__)

class FleetForm(ModelForm):
    class Meta:
        model = Fleet
        exclude = ['slug', 'created_by', 'org', 'members']

    def __init__(self, org_slug, *args, **kwargs):
        self.org_slug = org_slug
        self.helper = FormHelper()
        self.helper.form_method = 'post'

        self.helper.layout = Layout(
            'name',
            'description',
            'is_network',
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))

        super(FleetForm, self).__init__(*args, **kwargs)

    def clean_name(self):
        # Check that username is not used already
        name = self.cleaned_data.get('name')
        assert self.org_slug
        org = Org.objects.get(slug=self.org_slug)
        qs = Fleet.objects.filter(org=org, name=name)
        if self.instance:
            # Updating
            if qs.count() == 1 and self.instance.id != qs.first().id:
                raise forms.ValidationError('Fleet with name "{0}" already exist for {1}'.format(name, org.name))
        else:
            if qs.count():
                raise forms.ValidationError('Fleet with name "{0}" already exist for {1}'.format(name, org.name))
        return name


class FleetMembershipCreateForm(ModelForm):
    class Meta:
        model = FleetMembership
        exclude = ['fleet', 'created_on']

    def __init__(self, fleet, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'device',
            'always_on',
            'is_access_point',
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Add Device to fleet', css_class='btn btn-block btn-success submit'))

        super(FleetMembershipCreateForm, self).__init__(*args, **kwargs)
        existing_slugs = [d.slug for d in fleet.members.all()]
        self.fields['device'].queryset = Device.objects.filter(org=fleet.org, active=True)
        self.fields['device'].queryset = self.fields['device'].queryset.exclude(slug__in=existing_slugs)


class FleetMembershipUpdateForm(ModelForm):
    class Meta:
        model = FleetMembership
        exclude = ['fleet', 'device', 'created_on']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'always_on',
            'is_access_point',
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Update attributes', css_class='btn btn-block btn-success submit'))

        super(FleetMembershipUpdateForm, self).__init__(*args, **kwargs)


