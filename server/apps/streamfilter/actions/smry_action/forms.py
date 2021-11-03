from django import forms
from django.forms import ModelForm
from django.forms import ModelForm, SelectMultiple

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, ButtonHolder, HTML, Div

from apps.streamfilter.models import StreamFilterAction
from apps.org.models import Org
from apps.emailutil.utils import get_member_choice_list_by_org


class SummaryReportActionForm(ModelForm):
    generator = forms.ChoiceField(label="Report Summary Type",
                                  choices=[
                                      ('trip_update', 'Shipping - Trip Update'),
                                      ('end_of_trip', 'Shipping - End of Trip'),
                                  ],
                                  required=True)
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

    class Meta:
        model = StreamFilterAction
        fields = []

    def __init__(self, user, project, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h3>Generate Report Action</h3>'),
            'generator',
            HTML('<p>Notifications will be emailed to each recipient you add</p>'),
            HTML('<br>'),
            'recipients',
            HTML('<br>'),
            'extras',
        )
        super(SummaryReportActionForm, self).__init__(*args, **kwargs)
        if self.instance.extra_payload and 'rpt' in self.instance.extra_payload:
            self.fields['rpt'].initial = self.instance.extra_payload['rpt']
        org = project.org
        choices = [
            ('org:admin', 'All Organization Admins'),
            ('org:all', 'All Organization Members')
        ]
        choices += get_member_choice_list_by_org(org)
        self.fields['recipients'].choices = choices
        self.fields['recipients'].initial = []
        extras = []
        if self.instance.extra_payload and 'notification_recipients' in self.instance.extra_payload:
            if 'body' in self.instance.extra_payload:
                self.fields['body'].initial = self.instance.extra_payload['body']
            for item in self.instance.extra_payload['notification_recipients']:
                parts = item.split(':')
                if parts[0] == 'email':
                    extras.append(parts[1])
                else:
                    self.fields['recipients'].initial.append(item)
        if extras:
            self.fields['extras'].initial = '\n'.join(extras)

        if self.instance.extra_payload and 'generator' in self.instance.extra_payload:
            # Initialize generator drop down to existing value
            self.fields['generator'].initial = self.instance.extra_payload['generator']

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
        if len(notification_recipients) == 0:
            raise forms.ValidationError("Please enter recipient emails or select one of the notification recipient option")
        data['extra_payload'] = {
            "notification_recipients": notification_recipients,
            "generator": self.cleaned_data['generator']
        }
        return data




