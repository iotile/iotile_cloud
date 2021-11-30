from django import forms
from django.contrib.postgres.forms import SimpleArrayField
from django.forms import ModelForm

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Button, Div, Field, Layout, Submit

from apps.physicaldevice.models import Device
from apps.stream.models import StreamId, StreamVariable
from apps.streamfilter.models import StreamFilter

from .models import *


class ProjectForm(ModelForm):
    about = forms.CharField(label='Project Description', max_length=400, required=False,
                            widget=forms.Textarea(attrs={'rows': 5}))
    class Meta:
        model = Project
        exclude = ['slug', 'created_by', 'org', 'is_template', 'project_template', 'pages']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success btn-block submit'))

        super(ProjectForm, self).__init__(*args, **kwargs)


class ProjectCreateFromTemplateForm(forms.Form):
    org_slug = None
    new_name = forms.CharField(label='New Project Name', max_length=100, required=True)
    about = forms.CharField(label='Project Description', max_length=400, required=False,
                            widget=forms.Textarea(attrs={'rows': 5}))

    def __init__(self, org_slug,  *args, **kwargs):
        self.org_slug = org_slug
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        note = """
        <div class="alert alert-success alert-dismissible fade in" role="alert">
        As an <strong>alternative</strong> to creating a project now,
        you can use the <b>IOTile Companion App</b>
        to create a project as part of the device claiming process
        </div>
        """
        self.helper.layout = Layout(
            HTML(note),
            'new_name',
            'about',
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Create Project', css_class='btn btn-success submit'))

        super(ProjectCreateFromTemplateForm, self).__init__(*args, **kwargs)

    def clean_new_name(self):
        # Check that username is not used already
        new_name = self.cleaned_data.get('new_name')
        assert self.org_slug
        org = Org.objects.get(slug=self.org_slug)
        if Project.objects.filter(org=org, name=new_name).exists():
            raise forms.ValidationError('Project with name "{0}" already exist for {1}'.format(new_name, org.name))
        return new_name


class ProjectCloneForm(ModelForm):
    new_org = forms.ModelChoiceField(
        label='Destination Organization',
        queryset=Org.objects.none(),
        required=True
    )
    new_name = forms.CharField(label='New Project Name', max_length=100, required=True)

    user = None

    class Meta:
        model = Project
        fields = []

    def __init__(self, user, *args, **kwargs):
        self.user = user
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Clone Project', css_class='btn btn-success submit'))

        super(ProjectCloneForm, self).__init__(*args, **kwargs)

    def clean_new_name(self):

        new_name = self.cleaned_data.get('new_name')
        new_org = self.cleaned_data.get('new_org')
        if Project.objects.filter(org=new_org, name=new_name).exists():
            raise forms.ValidationError('This project name already exist in this organization')
        return new_name


class DeleteProjectForm(ModelForm):
    project_name = forms.CharField(label='Re-type the name of the Project to confirm', max_length=100, required=True)

    class Meta:
        model = Project
        fields = []

    def clean_project_name(self):
        # Check that the project name they typed is correct
        project_name = self.cleaned_data.get('project_name')
        if not Project.objects.filter(name=project_name).exists():
            raise forms.ValidationError('Project with name "{0}" does not exist'.format(project_name))
        return project_name

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'project_name',
        )
        self.helper.add_input(Submit('submit', 'Delete Project', css_class='btn btn-danger btn-block submit'))

        super(DeleteProjectForm, self).__init__(*args, **kwargs)


class ProjectStreamFilterForm(ModelForm):

    variable = forms.ModelChoiceField(
        label='Variable',
        queryset=StreamVariable.objects.none(),
        required=True
    )

    device = forms.ModelChoiceField(
        label='Device (All if left blank)',
        queryset=Device.objects.none(),
        required=False
    )

    states = SimpleArrayField(forms.CharField(max_length=1024),
                              label='States (State names are separated by comas ",")',
                              help_text='You can also create states later',
                              required=False)

    class Meta:
        model = StreamFilter
        fields = ['name', 'variable', 'device', 'input_stream']

    def __init__(self, project, *args, **kwargs):
        self.helper = FormHelper()
        self.project = project
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<h3>Filter Info</h3>'),
            'name',
            HTML(
                '<p>Filter will be executed when stream data arrives to the server from following variable and device. If device is empty, then the filter will be executed on data from all devices</p>'),
            Div(
                Div('variable', css_class='col-sm-6 col-xs-12'),
                Div('device', css_class='col-sm-6 col-xs-12'),
                css_class='row'
            ),
            'states',
            Field('input_stream', type="hidden")
        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))

        super(ProjectStreamFilterForm, self).__init__(*args, **kwargs)
        self.fields['variable'].queryset = project.variables.filter(app_only=False)
        self.fields['device'].queryset = project.devices.all()

    def clean(self):
        data = self.cleaned_data
        # Remove duplicate
        if data['states']:
            # Remove duplicate
            states = list(set(data['states']))
            data['states'] = states
        device = data['device']
        variable = data['variable']
        if device:
            streams = StreamId.objects.filter(device=device, variable=variable,
                                              project=self.project, block__isnull=True)
            if streams:
                stream = streams[0]
                elements = stream.slug.split('--')
                filter_stream_key = '--'.join(['f', ] + elements[1:])
                if StreamFilter.objects.filter(slug=filter_stream_key).count() > 0:
                    raise forms.ValidationError("Filter for this stream already exists")
                data['input_stream'] = stream
            else:
                raise forms.ValidationError("Stream corresponding to this device and variable does not exist")
        else:
            if StreamFilter.objects.filter(project=self.project, variable=variable, device=None).count() > 0:
                raise forms.ValidationError("Filter for this variable already exists")
        return data
