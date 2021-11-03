from django import forms
from django.forms import ModelForm
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, ButtonHolder, HTML, Div
from apps.streamfilter.models import StreamFilterAction


class CustomActionForm(ModelForm):
    sns_topic = forms.CharField(label="SNS Topic", max_length=1024, required=True)

    class Meta:
        model = StreamFilterAction
        fields = []

    def __init__(self, user, project, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h3>Custom Action</h3>'),
            'sns_topic',
        )
        super(CustomActionForm, self).__init__(*args, **kwargs)
        if self.instance.extra_payload and 'sns_topic' in self.instance.extra_payload:
            self.fields['sns_topic'].initial = self.instance.extra_payload['sns_topic']


    def clean(self):
        data = self.cleaned_data
        data['extra_payload'] = {
            "sns_topic": self.cleaned_data['sns_topic']
        }
        return data


