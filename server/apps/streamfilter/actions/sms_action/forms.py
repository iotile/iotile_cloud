import json
from django import forms
from django.forms import ModelForm
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, ButtonHolder, HTML, Div

from apps.streamfilter.models import StreamFilterAction


class SmsNotificationActionForm(ModelForm):
    phone_number = forms.RegexField(regex=r'^\+?1?\d{9,15}$',
                                    help_text='Expected format: \'+999999999\'. Up to 15 digits allowed.',
                                    error_messages={
                                        'required': 'Expected format: \'+999999999\'. Up to 15 digits allowed.'
                                    })
    msg = forms.CharField(
        label="Short message",
        required=True,
        widget=forms.Textarea
    )

    class Meta:
        model = StreamFilterAction
        fields = []

    def __init__(self, user, project, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h3>Send SMS Notification</h3>'),
            'phone_number',
            'msg',
            HTML('<h4>The following patterns will be replaced with proper values before sending message</h4>'),
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
        super(SmsNotificationActionForm, self).__init__(*args, **kwargs)
        if self.instance.extra_payload and 'number' in self.instance.extra_payload:
            self.fields['phone_number'].initial = self.instance.extra_payload['number']
            if 'body' in self.instance.extra_payload:
                self.fields['msg'].initial = self.instance.extra_payload['body']


    def clean(self):
        data = self.cleaned_data
        phone_number = self.cleaned_data['phone_number']
        data['extra_payload'] = {
            "body": self.cleaned_data['msg'],
            "number": self.cleaned_data['phone_number']
        }
        return data

