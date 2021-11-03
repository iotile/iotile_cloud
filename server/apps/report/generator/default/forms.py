from django import forms
from django.forms import ModelForm

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, HTML, Div

from apps.project.models import Project
from apps.vartype.models import VarTypeOutputUnit, VarType
from apps.report.models import UserReport


class DefaultConfigureForm(ModelForm):
    project = forms.ChoiceField(
        label="Select from list",
        choices=[],
        required=True
    )

    class Meta:
        model = UserReport
        fields = []

    def __init__(self, projects, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Add', css_class='btn btn-block btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h4>Default Report Configuration</h4>'),
            HTML('<br>'),
            HTML('<p>For every project you add as report source, the report generator will aggreage all streams for all devices in the project.</p>'),
            HTML('<p>You will have to add the variable filter after adding the project sources.</p>'),
            HTML('<br>'),
            'project',
            HTML('<br>'),
        )
        super(DefaultConfigureForm, self).__init__(*args, **kwargs)
        self.fields['project'].choices = [(p.slug, p.name) for p in projects]


class DefaultStep1Form(ModelForm):
    _cols = None
    name = forms.CharField(label='Header', max_length=20)
    var_type = forms.ChoiceField(
        label="Select from list",
        choices=[],
        required=True
    )

    class Meta:
        model = UserReport
        fields = []

    def __init__(self, cols, var_type_choices, *args, **kwargs):
        self._cols = cols
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Add', css_class='btn btn-block btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h4>Step 1 - Name column and select unit type</h4>'),
            HTML('<br>'),
            HTML('<p>Select the variable type you want the report to aggregate.</p>'),
            HTML('<p>You will be able to select multiple variables but all will have to match the variable type</p>'),
            HTML('<br>'),
            'name',
            'var_type',
            HTML('<br>'),
        )
        super(DefaultStep1Form, self).__init__(*args, **kwargs)
        self.fields['var_type'].choices = var_type_choices

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if self._cols:
            if name in [c['name'] for c in self._cols]:
                raise forms.ValidationError('Cannot add column with same name'.format(name))
        return name


class DefaultStep2Form(ModelForm):
    name = forms.CharField(label='Header', max_length=20)
    variables = forms.MultipleChoiceField(
        label="Select variables to aggregate together",
        choices=[],
        required=True
    )
    units = forms.ChoiceField(
        label="Select reporting units",
        choices=[],
        required=True
    )
    aggregate_type = forms.ChoiceField(
        label="Aggregation type",
        choices=[('sum', 'Accumulate values'), ('max', 'Max value'), ('min', 'Min value')],
        required=True
    )

    class Meta:
        model = UserReport
        fields = []

    def __init__(self, name, variable_choices, unit_choices, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Add', css_class='btn btn-block btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h4>Step 2 - Select device output and units</h4>'),
            HTML('<br>'),
            HTML('<p>Select the variables you want the report to aggregate together for this column.</p>'),
            HTML('<br>'),
            'name',
            'variables',
            Div(
                Div('units', css_class='col-sm-8 col-xs-12'),
                Div('aggregate_type', css_class='col-sm-4 col-xs-12'),
                css_class='row'
            ),
            HTML('<br>'),
        )
        super(DefaultStep2Form, self).__init__(*args, **kwargs)
        self.fields['variables'].choices = variable_choices
        self.fields['units'].choices = unit_choices
        self.initial['name'] = name
        self.fields['name'].widget.attrs['readonly'] = True


class DefaultReportGenerateForm(ModelForm):
    start = forms.DateTimeField(label='Start date', help_text='Format: YYYY-MM-DD HH:MM:SS *in your local time', required=False)
    end = forms.DateTimeField(label='End date', help_text='Format: YYYY-MM-DD HH:MM:SS', required=False)

    class Meta:
        model = UserReport
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Generate', css_class='btn btn-block btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h4>Generate Default Report</h4>'),
            HTML('<br>'),
            HTML('<h5>The report will be generated with the following custom date range</h5>'),
            Div(
                Div('start', css_class='col-xs-12 col-sm-6'),
                Div('end', css_class='col-xs-12 col-sm-6'),
                css_class='row'
            ),
            HTML('<br>'),
        )
        super(DefaultReportGenerateForm, self).__init__(*args, **kwargs)
