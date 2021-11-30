from django import forms
from django.forms import ModelForm

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Layout, Submit

from iotile_cloud.utils.gid import IOTileBlockSlug, IOTileDeviceSlug

from apps.report.models import UserReport


class TripUpdateConfigureForm(ModelForm):

    class Meta:
        model = UserReport
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Ok', css_class='btn btn-block btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h4>Trip Update Report Configuration</h4>'),
            HTML('<br>'),
            HTML('<br>'),
        )
        super(TripUpdateConfigureForm, self).__init__(*args, **kwargs)


class TripUpdateReportGenerateForm(ModelForm):
    source = forms.CharField(label='Device or Data Block ID (Slug)', max_length=38, required=True)

    class Meta:
        model = UserReport
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Generate', css_class='btn btn-block btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h4>Email Trip Update</h4>'),
            HTML('<br>'),
            HTML('<h5>This will look for any Trip Updates and will email the last one found</h5>'),
            'source',
            HTML('<br>'),
        )
        super(TripUpdateReportGenerateForm, self).__init__(*args, **kwargs)

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



