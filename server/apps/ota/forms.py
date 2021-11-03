from django import forms
from django.forms import ModelForm
from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Div, HTML

from .models import *
from .utils.selection import op_by_type, validate_value_by_type


class DeploymentRequestForm(ModelForm):
    selection_criteria_text = forms.CharField(
        label='Device Selection Criteria',
        required=False,
        help_text='One condition per line',
        widget=forms.Textarea
    )

    class Meta:
        model = DeploymentRequest
        # TODO: Decide if we need to enable Side Effect
        exclude = ['created_by', 'released_on', 'completed_on', 'org', 'side_effect']

    def __init__(self, org, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<br>'),
            Div(
                Div('script', css_class='col-xs-12 col-md-6'),
                Div('fleet', css_class='col-xs-12 col-md-6'),
                css_class='row'
            ),
            'selection_criteria_text',
            HTML('<h4>You will be able to publish the release later</h4>'),
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', _('Submit'), css_class='btn btn-success submit'))

        super(DeploymentRequestForm, self).__init__(*args, **kwargs)
        self.fields['script'].queryset = DeviceScript.objects.filter(
            Q(org__is_vendor=True) | Q(org=org)
        ).order_by('name')
        self.fields['fleet'].queryset = Fleet.objects.filter(org=org).order_by('name')
        if self.instance and self.instance.selection_criteria:
            self.fields['selection_criteria_text'].initial = '\n'.join(self.instance.selection_criteria)

    def clean(self):
        data = self.cleaned_data
        criteria_text = self.cleaned_data['selection_criteria_text']
        criteria_list = criteria_text.split('\n')
        cleaned_criteria = []
        # Format: “type:op:value”
        for row in criteria_list:
            row = row.strip()
            if row:
                content = row.split(':')
                if len(content) != 3:
                    raise forms.ValidationError("Each row must follow the following format: type:op:value")
                # Check the type
                if content[0] not in op_by_type.keys():
                    raise forms.ValidationError("Type (%s) is not valid input" % (content[0]))
                # Check the op
                if content[1] not in op_by_type[content[0]]:
                    raise forms.ValidationError("Op (%s) is not valid input" % (content[1]))
                # Check the value
                if not validate_value_by_type(content[0], content[2]):
                    raise forms.ValidationError("Value (%s) is not valid input for type (%s)" %
                                                (content[2], content[0]))
                cleaned_criteria.append(row)
        if len(cleaned_criteria) == 0:
            raise forms.ValidationError("Please enter at least one selection criteria")
        data['selection_criteria_text'] = cleaned_criteria
        return data


class DeploymentRequestReleaseForm(ModelForm):
    released_on = forms.DateTimeField(required=False, label='Release Date',
                                  help_text='*in your local time. Format: YYYY-MM-DD HH:MM:SS')

    class Meta:
        model = DeploymentRequest
        fields = ['released_on',]

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<br>'),
            HTML('<h3>Deployment Request: {{ object.id }}</h3>'),
            HTML('<br>'),
            HTML('<hr>'),
            'released_on',
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', _('Submit'), css_class='btn btn-success submit'))

        super(DeploymentRequestReleaseForm, self).__init__(*args, **kwargs)


class DeploymentRequestCompleteForm(ModelForm):

    class Meta:
        model = DeploymentRequest
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<br>'),
            HTML('<h3>Deployment Request: {{ object.id }}</h3>'),
            HTML('<br>'),
            HTML('<p>Released on {{ object.released_on }}</p>'),
            HTML('<hr>'),
            HTML('<h4>Are you sure you want to mark as completed?</h4>'),
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', _('Yes'), css_class='btn btn-success submit'))

        super(DeploymentRequestCompleteForm, self).__init__(*args, **kwargs)

