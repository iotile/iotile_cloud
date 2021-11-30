from django import forms
from django.forms import ModelForm

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, ButtonHolder, Div, Field, Layout, Submit

from apps.streamfilter.models import StreamFilterAction


class ReportActionForm(ModelForm):
    rpt = forms.CharField(label="Report ID", max_length=32, required=True)

    class Meta:
        model = StreamFilterAction
        fields = []

    def __init__(self, user, project, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h3>Generate Report Action</h3>'),
            'rpt',
        )
        super(ReportActionForm, self).__init__(*args, **kwargs)
        if self.instance.extra_payload and 'rpt' in self.instance.extra_payload:
            self.fields['rpt'].initial = self.instance.extra_payload['rpt']


    def clean(self):
        data = self.cleaned_data
        data['extra_payload'] = {
            "rpt": self.cleaned_data['rpt']
        }
        return data


