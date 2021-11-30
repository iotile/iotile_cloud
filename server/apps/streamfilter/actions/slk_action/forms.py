import json

from django import forms
from django.conf import settings
from django.forms import ModelForm
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, ButtonHolder, Div, Field, Layout, Submit

from apps.streamfilter.models import StreamFilterAction


class SlackNotificationActionForm(ModelForm):
    slack_webhook = forms.CharField(label="Slack Incoming WebHook URL", max_length=1024, required=True)
    custom_note = forms.CharField(label="Custom Note (if left empty, a default message will be sent)",
                                  max_length=1024, required=False,
                                  widget=forms.Textarea(attrs={'cols': '40', 'rows': '4'}))

    class Meta:
        model = StreamFilterAction
        fields = []

    def __init__(self, user, project, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h3>Send Slack Notification</h3>'),
            'slack_webhook',
            HTML('<p>See <a href="https://api.slack.com/incoming-webhooks" style="color:blue">Slack WebHook integration</a></p>'),
            'custom_note',
            HTML('<h4>The following patterns will be replaced with proper values before posting message</h4>'),
            HTML('<ul>'),
            HTML('<li>{label}: Stream Filter Label'),
            HTML('<li>{state}: Stream Filter state'),
            HTML('<li>{on}: "into" if entering a State or "out of" if exiting one'),
            HTML('<li>{stream}: Stream Label (or ID)'),
            HTML('<li>{ts}: Data Timestamp'),
            HTML('<li>{value}: Data Value (with units)'),
            HTML('</ul>'),
            HTML('<p><b>Example</b></p>'),
            HTML('<p><i>{label} has transitioned {on} {state}. New value is {value} @ {ts}</i></p>'),
        )
        super(SlackNotificationActionForm, self).__init__(*args, **kwargs)
        if self.instance.extra_payload and 'slack_webhook' in self.instance.extra_payload:
            self.fields['slack_webhook'].initial = self.instance.extra_payload['slack_webhook']
            if 'custom_note' in self.instance.extra_payload:
                self.fields['custom_note'].initial = self.instance.extra_payload['custom_note']


    def clean(self):
        data = self.cleaned_data
        note = ""
        if "custom_note" in self.cleaned_data and self.cleaned_data['custom_note']:
            note = self.cleaned_data['custom_note']
        data['extra_payload'] = {
            "custom_note": note,
            "slack_webhook": self.cleaned_data['slack_webhook']
        }
        return data

