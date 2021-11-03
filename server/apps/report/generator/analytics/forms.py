import json
from django import forms
from django.forms import ModelForm

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, HTML, Div

from iotile_cloud.utils.gid import IOTileDeviceSlug, IOTileBlockSlug

from apps.report.models import UserReport

from .choices import template_choices


class AnalyticsConfigureForm(ModelForm):
    template = forms.ChoiceField(
        label="Template: Select from list",
        choices=template_choices,
        required=True
    )

    class Meta:
        model = UserReport
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Ok', css_class='btn btn-block btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h4>Analytics Summary Report Configuration</h4>'),
            HTML('<br>'),
            HTML('<p>Analytics Reports are based on pre-defined templates.</p>'),
            HTML('<p>You need to pick and configure the decired template.</p>'),
            HTML('<br>'),
            'template',
            HTML('<br>'),
        )
        super(AnalyticsConfigureForm, self).__init__(*args, **kwargs)

    def set_config(self, report):
        template = self.cleaned_data.get('template')
        report.config['template'] = template
        report.save()


class AnalyticsReportGenerateForm(ModelForm):
    source = forms.CharField(label='Device or Data Block ID (Slug)', max_length=38, required=True)
    extra_args = forms.CharField(label='Additional Template Arguments', widget=forms.Textarea, required=False)

    class Meta:
        model = UserReport
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Generate', css_class='btn btn-block btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h4>Generate Analytics Report</h4>'),
            HTML('<br>'),
            HTML('<h5>This will generate an Analytics Report based on the given Template</h5>'),
            'source',
            'extra_args',
            HTML('<br>'),
        )
        super(AnalyticsReportGenerateForm, self).__init__(*args, **kwargs)

    def clean_source(self):
        # Check that username is not used already
        source = self.cleaned_data.get('source')
        if source[0] == 'd':
            slug_class = IOTileDeviceSlug
        elif source[0] == 'b':
            slug_class = IOTileBlockSlug
        else:
            raise forms.ValidationError('Illegal device or data block slug: {}'.format(source))

        try:
            obj_slug = slug_class(source)
        except ValueError:
            raise forms.ValidationError('Illegal device or data block slug: {}'.format(source))

        return obj_slug

    def clean_extra_args(self):
        if 'extra_args' in self.cleaned_data:
            extra_args = self.cleaned_data.get('extra_args')
            try:
                return json.loads(extra_args)
            except Exception as e:
                forms.ValidationError(str(e))
        return None

