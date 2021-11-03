import json
from django import forms
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Div, HTML
from apps.utils.codemirror.widgets import JsonEditor

from .models import ConfigAttribute


class ConfigAttributeForm(forms.ModelForm):
    txt_data = forms.CharField(label='Data (Json)', max_length=10000,
                                widget=JsonEditor(attrs={'style': 'width: 100%; height: 200pt;'}))

    class Meta:
        model = ConfigAttribute
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', _('Save'), css_class='btn btn-success btn-block submit'))
        super(ConfigAttributeForm, self).__init__(*args, **kwargs)
        if self.instance:
            formatted_data = json.dumps(self.instance.data, sort_keys=True, indent=2)
            self.fields['txt_data'].initial = formatted_data

    def clean_txt_data(self):
        txt_data = self.cleaned_data.get('txt_data')
        try:
            return json.loads(txt_data)
        except Exception as e:
            raise forms.ValidationError('Syntax Error: {}'.format(e))
        return txt_data
