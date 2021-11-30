import json
import logging

from django import forms
from django.conf import settings
from django.forms import ModelForm, SelectMultiple

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Layout, Submit

from apps.emailutil.utils import get_member_choice_list_by_org
from apps.utils.aws.sqs import SqsPublisher
from apps.utils.forms.fields import FormattedJsonField

from .generator.analytics.choices import template_choices
from .models import GeneratedUserReport, UserReport

logger = logging.getLogger(__name__)


class UserReportAdminForm(forms.ModelForm):

    config = FormattedJsonField(
        widget=forms.Textarea(attrs={'rows': '10', 'cols': '80'})
    )

    class Meta:
        model = UserReport
        exclude=['created_by', 'created_on']


class UserReportCreateForm(ModelForm):

    class Meta:
        model = UserReport
        fields = ['label', 'generator', ]

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Create', css_class='btn btn-block btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h3>New periodic report</h3>'),
            Div(
                Div('label', css_class='col-sm-12 col-xs-12'),
                css_class='row'
            ),
            'generator'
        )
        super(UserReportCreateForm, self).__init__(*args, **kwargs)


class UserReportAddRecipientForm(ModelForm):
    recipients = forms.MultipleChoiceField(
        label='Organization Members (Select from list)',
        help_text='Hold down "Control", or "Command" to select more than one.',
        widget=SelectMultiple(attrs={'size':'10'}),
        choices=[],
        required=True
    )
    extras = forms.CharField(
        label='Other emails (not members of the Organization)',
        required=False,
        help_text='One email address per row (e.g. joe@example.com)',
        widget=forms.Textarea
    )

    class Meta:
        model = UserReport
        fields = []

    def __init__(self, org, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Add', css_class='btn btn-block btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h4>Report Email Recipients</h4>'),
            HTML('<br>'),
            HTML('<p>Generated reports will be emailed to each recipient you add</p>'),
            HTML('<br>'),
            'recipients',
            HTML('<br>'),
            'extras',
            HTML('<br>'),
        )
        super(UserReportAddRecipientForm, self).__init__(*args, **kwargs)
        choices = [
            ('org:admin', 'All Organization Admins'),
            ('org:all', 'All Organization Members')
        ]
        choices += get_member_choice_list_by_org(org)
        self.fields['recipients'].choices = choices
        self.fields['recipients'].initial = []
        extras = []
        for item in self.instance.notification_recipients:
            parts = item.split(':')
            if parts[0] == 'email':
                extras.append(parts[1])
            else:
                self.fields['recipients'].initial.append(item)
        if extras:
            self.fields['extras'].initial = '\n'.join(extras)


class GeneratedUserReportForm(ModelForm):
    template = forms.ChoiceField(
        label="Template: Select from list",
        choices=template_choices,
        required=True
    )
    extra_args = FormattedJsonField(
        widget=forms.Textarea(attrs={'rows': '10', 'cols': '80'}),
        label = 'Additional Template Arguments',
        required = False,
        help_text = 'Example {"stream": "temp", "units": "Celsius"}'
    )

    class Meta:
        model = GeneratedUserReport
        fields = ['label']

    def __init__(self, ref, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Ok', css_class='btn btn-block btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h4>Analytics Summary Report Configuration</h4>'),
            HTML('<br>'),
            HTML('<p>Analytics Reports are based on pre-defined templates.</p>'),
            HTML('<p>You need to pick and configure the decired template.</p>'),
            HTML('<br>'),
            'label',
            'template',
            'extra_args',
            HTML('<br>'),
        )
        super(GeneratedUserReportForm, self).__init__(*args, **kwargs)
        self.fields['extra_args'].initial = {}

    def schedule_analysis(self, generated_report):
        report_worker_payload = {
            'report': str(generated_report.id),
            'template': self.cleaned_data.get('template'),
            'group_slug': str(generated_report.source_ref),
            'user': generated_report.created_by.email,
            'token': generated_report.created_by.jwt_token,
            'args': self.cleaned_data.get('extra_args')
        }
        logger.info(report_worker_payload)

        sqs = SqsPublisher(getattr(settings, 'SQS_ANALYTICS_QUEUE_NAME'))
        sqs.publish(payload=report_worker_payload)


class GeneratedUserReportEditForm(ModelForm):

    class Meta:
        model = GeneratedUserReport
        fields = ['label', 'public']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Ok', css_class='btn btn-block btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h4>Generated Report Settings</h4>'),
            HTML('<br>'),
            'label',
            HTML('<br>'),
            'public',
            HTML('<p>If set to public, a public link will be available to'),
            HTML('send to people without access to IOTile Cloud.</p>'),
            HTML('<br>'),
        )
        super(GeneratedUserReportEditForm, self).__init__(*args, **kwargs)
