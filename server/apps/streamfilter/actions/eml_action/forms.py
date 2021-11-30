import json

from django import forms
from django.contrib.postgres.forms import SimpleArrayField
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.forms import ModelForm, SelectMultiple

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, ButtonHolder, Div, Field, Layout, Submit

from apps.emailutil.utils import get_member_choice_list_by_org
from apps.streamfilter.models import StreamFilterAction


class EmailNotificationActionForm(ModelForm):
    recipients = forms.MultipleChoiceField(
        label='Organization Members (Select from list)',
        help_text='Hold down "Control", or "Command" to select more than one.',
        widget=SelectMultiple(attrs={'size':'8'}),
        choices=[],
        required=True
    )
    extras = forms.CharField(
        label='Other emails (not members of the Organization)',
        required=False,
        help_text='One email address per row (e.g. joe@example.com)',
        widget=forms.Textarea(attrs={'cols': '40', 'rows': '4'})
    )

    # Extra fields only for Send Notification Action
    body = forms.CharField(label="Custom Body (if left empty, a default message will be sent)", max_length=1024, required=False,
                                  widget=forms.Textarea(attrs={'cols': '40', 'rows': '4'}))

    class Meta:
        model = StreamFilterAction
        fields = []

    def __init__(self, user, project, *args, **kwargs):
        self.user = user
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h4>Send Email Notification</h4>'),
            HTML('<br>'),
            HTML('<p>Notifications will be emailed to each recipient you add</p>'),
            HTML('<br>'),
            'recipients',
            HTML('<br>'),
            'extras',
            HTML('<br>'),
            'body',
            HTML('<h5>The following patterns will be replaced with proper values before sending email</h5>'),
            HTML('<ul>'),
            HTML('<li>{label}: Stream Filter Label'),
            HTML('<li>{state}: Stream Filter state'),
            HTML('<li>{on}: "into" if entering a State or "out of" if exiting one'),
            HTML('<li>{project}: Project name'),
            HTML('<li>{device}: Device label (or ID)'),
            HTML('<li>{stream}: Stream Label (or ID)'),
            HTML('<li>{ts}: Data Timestamp'),
            HTML('<li>{value}: Data Value (with units)'),
            HTML('</ul>'),
            HTML('<p><b>Example</b></p>'),
            HTML('<p><i>{label} has transitioned {on} {state}. New value is {value} @ {ts}</i></p>'),
        )
        super(EmailNotificationActionForm, self).__init__(*args, **kwargs)
        org = project.org
        choices = [
            ('org:admin', 'All Organization Admins'),
            ('org:all', 'All Organization Members')
        ]
        choices += get_member_choice_list_by_org(org)
        self.fields['recipients'].choices = choices
        self.fields['recipients'].initial = []
        extras = []
        if self.instance.extra_payload and 'notification_recipient' in self.instance.extra_payload:
            if 'body' in self.instance.extra_payload:
                self.fields['body'].initial = self.instance.extra_payload['body']
            for item in self.instance.extra_payload['notification_recipient']:
                parts = item.split(':')
                if parts[0] == 'email':
                    extras.append(parts[1])
                else:
                    self.fields['recipients'].initial.append(item)
        if extras:
            self.fields['extras'].initial = '\n'.join(extras)

    def clean(self):
        data = self.cleaned_data
        recipients = self.cleaned_data['recipients']
        notification_recipients = recipients
        extras = self.cleaned_data['extras']
        extra_emails = extras.split('\n')
        for extra_email in extra_emails:
            extra_email = extra_email.strip()
            if extra_email:
                notification_recipients.append('email:{}'.format(extra_email))
        body = None
        if "body" in self.cleaned_data and self.cleaned_data['body']:
            body = self.cleaned_data['body']
        if len(notification_recipients) == 0:
            raise forms.ValidationError("Please enter recipient emails or select one of the notification recipient option")
        data['extra_payload'] = {
            "notification_recipient": notification_recipients,
            "body": body
        }
        return data

