import json
import logging

from django import forms
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Layout, Submit

from apps.utils.aws.s3 import download_text_as_object, upload_text_from_object
from apps.utils.codemirror.widgets import JsonEditor, SgfEditor

from .models import SensorGraph

logger = logging.getLogger(__name__)


class SensorGraphForm(forms.ModelForm):

    class Meta:
        model = SensorGraph
        fields = [
            'name', 'app_tag', 'org', 'active', 'description', 
            'major_version', 'minor_version', 'patch_version'
        ]

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Div(
                Div('name', css_class='col-sm-8'),
                Div('app_tag', css_class='col-sm-4'),
                css_class='row'
            ),
            Div(
                Div('org', css_class='col-sm-8'),
                css_class='row'
            ),
            'active',
            HTML('<br>'),
            Div(
                Div('major_version', css_class='col-xs-4'),
                Div('minor_version', css_class='col-xs-4'),
                Div('patch_version', css_class='col-xs-4'),
                css_class='row'
            ),
            'description',
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', _('Submit'), css_class='btn btn-default submit'))

        super(SensorGraphForm, self).__init__(*args, **kwargs)


class SensorGraphUiExtraForm(forms.ModelForm):
    extra = forms.CharField(label='uiExtra (Json)', max_length=5000,
                            widget=JsonEditor(attrs={'style': 'width: 100%; height: 100%;'}))

    class Meta:
        model = SensorGraph
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Save', css_class='btn btn-success btn-block submit'))
        super(SensorGraphUiExtraForm, self).__init__(*args, **kwargs)
        if self.instance:
            formatted_data = json.dumps(self.instance.ui_extra, sort_keys=True, indent=2)
            self.fields['extra'].initial = formatted_data

    def clean_extra(self):
        extra = self.cleaned_data.get('extra')
        try:
            return json.loads(extra)
        except Exception as e:
            raise forms.ValidationError('Syntax Error: {}'.format(e))


class SensorGraphSgfForm(forms.ModelForm):
    sg_file = forms.CharField(label='File',
                              widget=SgfEditor(attrs={'style': 'width: 100%; height: 100%;'}))

    class Meta:
        model = SensorGraph
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Save', css_class='btn btn-success btn-block submit'))
        super(SensorGraphSgfForm, self).__init__(*args, **kwargs)
        if self.instance:
            sgf = self.instance.sgf
            if sgf:
                file_obj = download_text_as_object(
                    bucket=sgf.bucket,
                    key=sgf.key
                )
                self.fields['sg_file'].initial = str(file_obj)
                self.fields['sg_file'].label = self.instance.sgf.title

    def save(self, commit=True):
        instance = super(SensorGraphSgfForm, self).save(commit=False)
        sg_file = self.cleaned_data['sg_file']
        logger.info('Uploading SGF to {}'.format(instance.sgf.key))
        upload_text_from_object(data=sg_file, bucket=instance.sgf.bucket, key=instance.sgf.key)
        if commit:
            instance.save()
        return instance
