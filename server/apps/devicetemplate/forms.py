from django.forms import ModelForm
from django import forms
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Div, HTML

from .models import *

class DeviceTemplateForm(ModelForm):
    released_on = forms.DateField(label=_('Release Date'), help_text='Format: YYYY-MM-DD HH:MM:SS')

    class Meta:
        model = DeviceTemplate
        exclude = ['slug', 'created_by', 'components',]

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Div(
                Div('external_sku', css_class='col-sm-8'),
                Div('family', css_class='col-sm-4'),
                css_class='row'
            ),
            Div(
                Div('internal_sku', css_class='col-sm-8'),
                Div('os_tag', css_class='col-sm-4'),
                css_class='row'
            ),
            Div(
                Div('org', css_class='col-sm-8'),
                Div('released_on', css_class='col-sm-4'),
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
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success btn-block submit'))

        super(DeviceTemplateForm, self).__init__(*args, **kwargs)
        if self.instance.org_id:
            self.fields['org'].queryset = Org.objects.filter(id=self.instance.org_id)
        else:
            self.fields['org'].queryset = Org.objects.filter(is_vendor=True).order_by('name')


class AddComponentToDeviceForm(ModelForm):
    slot_number = forms.IntegerField()
    components = forms.ModelChoiceField(label=_('Components'),
                                        queryset=Component.objects.all())
    class Meta:
        model = DeviceTemplate
        fields = ['components',]

    def __init__(self, *args, **kwargs):
        super(AddComponentToDeviceForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-default submit'))

    def get_component_list(self, device):
        if device:
            component_qs = Component.objects.exclude(id__in=device.components.all())
            component_qs = component_qs.filter(active=True)
        else:
            component_qs = Component.objects.filter(active=True)

        return component_qs

    def get_component(self):
        return self.cleaned_data['components']
