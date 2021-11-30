import json

from django import forms

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Layout, Submit

from .common import ACTION_CHOICES


class ScheduleWorkerForm(forms.Form):
    action = forms.ChoiceField(
        label="Choose an action to schedule",
        choices=[],
        required=True,
    )
    args = forms.CharField(
        label="Arguments for the action (Json formatted string)",
        required=True,
        widget=forms.Textarea,
        help_text="example : {\"message\":\"hello\"}"
    )

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Schedule Task', css_class='btn btn-block btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h2>Using queue: {{queue}}</h2><br>'),
            'action',
            'args',
        )
        super(ScheduleWorkerForm, self).__init__(*args, **kwargs)
        self.fields['action'].choices = sorted(ACTION_CHOICES, key= lambda x: x[1])



class CleanupWorkerForm(forms.Form):
    min_count = forms.IntegerField(initial=0)

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Clean Cache', css_class='btn btn-block btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h2>Cleanup worker cache</h2><br><br>'),
            HTML('<p>Clean any worker with total task count less than:</p>'),
            'min_count',
            HTML('<br>')
        )
        super(CleanupWorkerForm, self).__init__(*args, **kwargs)

