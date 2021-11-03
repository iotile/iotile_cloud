from django.forms import ModelForm, CharField
from django.core.validators import ValidationError
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, ButtonHolder, Button, Div, Fieldset, HTML
from crispy_forms.bootstrap import InlineField, AppendedText, PrependedText, PrependedAppendedText

from apps.utils.gid.convert import gid2int, int16gid
from django import forms
from apps.utils.timezone_utils import str_utc

from .models import *


class StreamDataDeleteForm(ModelForm):
    date_from = forms.DateTimeField(required=False, label='Start date: (optional)', help_text='Format: YYYY-MM-DD HH:MM:SS *in your local time')
    date_to = forms.DateTimeField(required=False, label='End date: (optional)', help_text='Format: YYYY-MM-DD HH:MM:SS *in your local time')

    class Meta:
        model = StreamId
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<h2>Stream slug: {{stream_slug}}</h2><br>'),
            HTML('<h5>Select a start date and an end date for deletion</h5>'),
            'date_from', 'date_to',
            HTML('<br>'),
            ButtonHolder(
                Submit('delete_data', 'Submit', css_class='btn-block btn-success submit')
            )
        )
        super(StreamDataDeleteForm, self).__init__(*args, **kwargs)

    def clean(self):
        if self.cleaned_data.get('date_from') and self.cleaned_data.get('date_to') and self.cleaned_data.get('date_from') > self.cleaned_data.get('date_to'):
            raise forms.ValidationError("The start date must be before the end date")
        return self.cleaned_data


class StreamDataDeleteAllForm(ModelForm):
    class Meta:
        model = StreamId
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Confirm Delete', css_class='btn btn-default submit'))
        super(StreamDataDeleteAllForm, self).__init__(*args, **kwargs)


class StreamDataDeleteConfirmForm(ModelForm):
    class Meta:
        model = StreamId
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            ButtonHolder(
                Submit('submit', 'Confirm delete', css_class='btn btn-danger submit'),
            )
        )
        super(StreamDataDeleteConfirmForm, self).__init__(*args, **kwargs)


class StreamVariableForm(ModelForm):
    lid_hex = CharField(label='ID (Hex)', max_length=4)
    class Meta:
        model = StreamVariable
        fields = ['name', 'lid_hex', 'about', 'var_type', 'app_only', 'web_only']

    def __init__(self, project, *args, **kwargs):
        self.project = project
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Div(
                Div('name', css_class='col-sm-8 col-xs-12'),
                Div(Field('lid_hex', placeholder='e.g. 100b or 5001'), css_class='col-sm-4 col-xs-12'),
                css_class='row'
            ),
            Div(
                Div('about', css_class='col-sm-8 col-xs-12'),
                Div('var_type', css_class='col-sm-4 col-xs-12'),
                css_class='row'
            ),
            'app_only',
            'web_only',
            HTML('<br>')
        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-default submit'))

        super(StreamVariableForm, self).__init__(*args, **kwargs)

        if 'instance' in kwargs:
            variable = kwargs['instance']
            if variable:
                self.initial['lid_hex'] = int16gid(variable.lid)

    def clean_lid_hex(self):
        lid_hex = self.cleaned_data.get('lid_hex')
        lid = gid2int(lid_hex)
        if self.instance:
            if self.instance.lid == lid:
                return lid_hex
        try:
            var = StreamVariable.objects.get(lid=lid, project=self.project)
            logger.error('User is trying to create existing var id: {0}'.format(var))
            raise ValidationError(_('Var ID already used. IDs most be unique for a given project'))
        except StreamVariable.DoesNotExist:
            # Now check that this is a HEX number
            return lid_hex

    def get_lid(self):
        lid_hex = self.cleaned_data.get('lid_hex')
        return gid2int(lid_hex)

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if self.instance:
            if self.instance.name == name:
                return name
        try:
            var = StreamVariable.objects.get(name=name, project=self.project)
            logger.error('User is trying to create existing name: {0}'.format(var))
            raise ValidationError(_('Name already used. Stream names most be unique for a given project'))
        except StreamVariable.DoesNotExist:
            return name


class StreamVariableUnitsForm(ModelForm):
    raw_value_format = forms.ChoiceField(
        label='Value Type',
        choices=[(CTYPE_TO_RAW_FORMAT[t], t) for t in CTYPE_TO_RAW_FORMAT.keys()],
        required=True
    )
    class Meta:
        model = StreamVariable
        fields = ['multiplication_factor', 'division_factor', 'offset', 'input_unit', 'output_unit',
                  'raw_value_format', 'decimal_places', ]

    def __init__(self, project, *args, **kwargs):
        self.project = project
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<h4>IO Configurations can be overwritten at the device level (stream)</h4>'),
            HTML('<hr>'),
            Fieldset("Project Defaults: Device Input Factor (e.g. Pulses per Units):",
                     Div(
                         Div(PrependedText('multiplication_factor', 'value * (', placeholder="Multiplication Factor"),
                             title='Multiple stream value by this amount', css_class='col-sm-4 col-xs-12'),
                         Div(PrependedAppendedText('division_factor', '/', ')'),
                             title='Divide stream value by this amount', css_class='col-sm-4 col-xs-12'),
                         Div(PrependedText('offset', '+', placeholder="Offset"),
                             css_class='col-sm-4 col-xs-12'),
                         css_class='row'
                     ),
            ),
            HTML('<br>'),
            Fieldset("Device Input Units and Type:",
                     Div(
                         Div('input_unit', css_class='col-sm-6 col-xs-12'),
                         Div('raw_value_format', css_class='col-sm-6 col-xs-12'),
                         css_class='row'
                     )
            ),
            HTML('<br>'),
            Fieldset("Display Format:",
                     Div(
                         Div('output_unit', css_class='col-sm-6 col-xs-12'),
                         Div('decimal_places', css_class='col-sm-6 col-xs-12'),
                         css_class='row'
                     )
            )
        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-default submit'))

        super(StreamVariableUnitsForm, self).__init__(*args, **kwargs)
        variable = kwargs['instance']
        if variable:
            self.fields['input_unit'].queryset = VarTypeInputUnit.objects.filter(var_type=variable.var_type)
            self.fields['output_unit'].queryset = VarTypeOutputUnit.objects.filter(var_type=variable.var_type)


class StreamIdDataMdoForm(ModelForm):
    raw_value_format = forms.ChoiceField(
        label='Value Type',
        choices=[(CTYPE_TO_RAW_FORMAT[t], t) for t in CTYPE_TO_RAW_FORMAT.keys()],
        required=True
    )
    class Meta:
        model = StreamId
        fields = ['data_label', 'multiplication_factor', 'division_factor', 'offset',
                  'raw_value_format', 'input_unit', 'output_unit', 'enabled']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Fieldset("Stream Label (or alias)",
                     'data_label',
            ),
            HTML('<hr>'),
            HTML('<h5>Variable Settings</h5>'),
            HTML('<ul>'),
            HTML('<li>Variable Type: {{ stream.var_type }}</li>'),
            HTML('<li>Data Type: {{ stream.get_data_type_display }}</li>'),
            HTML('</ul>'),
            HTML('<hr>'),
            Fieldset("Device Input Setup (e.g. Pulses per Units):",
                     Div(
                         Div(PrependedText('multiplication_factor', 'value * ('),
                             title='Multiple stream value by this amount', css_class='col-sm-4 col-xs-12'),
                         Div(PrependedAppendedText('division_factor', '/', ')'),
                             title='Divide stream value by this amount', css_class='col-sm-4 col-xs-12'),
                         Div(PrependedText('offset', '+'),
                             css_class='col-sm-4 col-xs-12'),
                         css_class='row'
                     ),
            ),
            Fieldset("Device Input Units and Type:",
                     Div(
                         Div('input_unit', css_class='col-sm-6 col-xs-12'),
                         Div('raw_value_format', css_class='col-sm-6 col-xs-12'),
                         css_class='row'
                     )
            ),
            'enabled',
            HTML('<hr>'),
            Fieldset("Device Display Setup",
                     'output_unit'
            ),
        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-default submit'))

        super(StreamIdDataMdoForm, self).__init__(*args, **kwargs)
        stream = kwargs['instance']
        if stream:
            variable = stream.variable
            if variable:
                self.fields['input_unit'].queryset = VarTypeInputUnit.objects.filter(var_type=variable.var_type)
                self.fields['output_unit'].queryset = VarTypeOutputUnit.objects.filter(var_type=variable.var_type)

    def clean_division_factor(self):
        type = self.cleaned_data.get('mdo_type')
        d = self.cleaned_data.get('division_factor')
        if type != 'V' and not d:
            raise ValidationError(_('Division most be set'))
        return d

    def clean_multiplication_factor(self):
        type = self.cleaned_data.get('mdo_type')
        m = self.cleaned_data.get('multiplication_factor')
        if type != 'V' and not m:
            raise ValidationError(_('Multiplication most be set'))
        return m


class StreamIdEventMdoForm(ModelForm):
    raw_value_format = forms.ChoiceField(
        label='Value Type',
        choices=[(CTYPE_TO_RAW_FORMAT[t], t) for t in CTYPE_TO_RAW_FORMAT.keys()],
        required=True
    )
    class Meta:
        model = StreamId
        fields = ['data_label',
                  'enabled']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Fieldset("Stream Label (or alias)", 'data_label',),
            HTML('<hr>'),
            HTML('<h4>This is an encoded Stream Event</h4>'),
            HTML('<hr>'),
            HTML('<h5>Variable Settings</h5>'),
            HTML('<ul>'),
            HTML('<li>Variable Type: {{ stream.var_type }}</li>'),
            HTML('<li>Data Type: {{ stream.get_data_type_display }}</li>'),
            HTML('</ul>'),
            HTML('<hr>'),
            'enabled',
            HTML('<hr>'),
        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-default submit'))

        super(StreamIdEventMdoForm, self).__init__(*args, **kwargs)


class StreamIdDisableForm(ModelForm):
    class Meta:
        model = StreamId
        fields = ['enabled']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<h2>Do you want to change data collection settings?</h2>'),
            'enabled',
            HTML('<h2>Note: You can re-enable data collection at any time, but data will only be recorded for periods when the stream was enabled.</h2>'),

        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-default submit'))

        super(StreamIdDisableForm, self).__init__(*args, **kwargs)
