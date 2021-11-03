import json
from django import forms
from django.forms import ModelForm
from django.contrib.auth import get_user_model
from django.core.validators import ValidationError

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, ButtonHolder, HTML, Div

from apps.streamfilter.models import StreamFilterAction
from apps.stream.models import StreamId, StreamVariable
from apps.project.models import Project
from apps.utils.gid.convert import int16gid

user_model = get_user_model()


class DeriveStreamActionForm(ModelForm):
    lid_hex = forms.CharField(label='Output Project Stream Variable',
                              required=True,
                              help_text='Will create a project stream (if it does not exist). Use four digit HEX value.')

    extra_payload = forms.CharField(initial="", required=False)
    project = forms.ModelChoiceField(queryset=Project.objects.all(), required=False)
    user = forms.ModelChoiceField(queryset=user_model.objects.all(), required=False)
    output_stream = forms.ModelChoiceField(queryset=StreamId.objects.all(), required=False)

    class Meta:
        model = StreamFilterAction
        fields = ['lid_hex', 'extra_payload', 'output_stream']

    def __init__(self, user, project, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h3>Accumulation</h3>'),
            'lid_hex',
            Field('extra_payload', type="hidden"),
            Field('user', type="hidden"),
            Field('project', type="hidden"),
            Field('output_stream', type="hidden")
        )
        super(DeriveStreamActionForm, self).__init__(*args, **kwargs)
        self.fields['project'].initial = project
        self.fields['user'].initial = user
        if self.instance.extra_payload and 'local_id' in self.instance.extra_payload:
            self.fields['lid_hex'].initial = int16gid(self.instance.extra_payload['local_id'])

    def clean_lid_hex(self):
        lid_hex = self.cleaned_data.get('lid_hex')
        try:
            lid = int(lid_hex, 16)
        except ValueError:
            raise ValidationError('Needs a four digit HEX number. e.g. 5555')
        return lid

    def clean(self):
        data = self.cleaned_data
        project = self.cleaned_data.get('project')
        user = self.cleaned_data.get('user')

        lid = self.cleaned_data.get('lid_hex')
        if not lid:
            return data
        variable, _ = StreamVariable.objects.get_or_create(
            project=project,
            lid = lid,
            defaults={
                'name': 'Derived - {}'.format(lid),
                'org': project.org,
                'created_by': user
            },
        )

        stream, _ = StreamId.objects.get_or_create(
            project=project,
            variable=variable,
            device=None,
            block=None,
            defaults={
                'data_label': variable.name,
                'var_lid': lid,
                'var_name': variable.name,
                'org': project.org,
                'mdo_type': 'S',
                'multiplication_factor': 1,
                'division_factor': 1,
                'offset': 0.0,
                'created_by': user
            },
        )
        data['extra_payload'] = {
            'local_id': lid,
            'output_stream': stream.slug
        }

        return data