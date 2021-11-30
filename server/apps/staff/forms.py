import json
from datetime import datetime

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.postgres.forms import SimpleArrayField
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Q
from django.forms import ModelForm

from crispy_forms.bootstrap import FieldWithButtons
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, ButtonHolder, Div, Field, Layout, Submit

from apps.devicetemplate.models import DeviceTemplate
from apps.org.models import Org
from apps.physicaldevice.claim_utils import DEFAULT_IOTILE_DEVICE_NAME_FORMAT
from apps.physicaldevice.models import Device
from apps.physicaldevice.state import DEVICE_STATE_CHOICES
from apps.project.models import Project
from apps.sensorgraph.models import SensorGraph
from apps.stream.models import StreamId

user_model = get_user_model()


class NewUserForm(forms.Form):
    name = forms.CharField(label='Full Name', max_length=100, required=False)
    username = forms.CharField(label='Username', max_length=100, required=True)
    email = forms.EmailField(label='Email', max_length=100, required=True)
    temp_password = forms.CharField(label='Temp Password', max_length=100, required=True)
    org = forms.ModelChoiceField(
        label='Add as member of',
        queryset=Org.objects.all().order_by('name'),
        empty_label='(No Organization)',
        required=False
    )

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML("<h4>Note that you can instead invite users from the Organization Membership pages</h4>"),
            HTML('<br>'),
            'name',
            'username',
            'email',
            'temp_password',
        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))

        super(NewUserForm, self).__init__(*args, **kwargs)

    def clean_username(self):
        # Check that username is not used already
        username = self.cleaned_data.get('username')
        if user_model.objects.filter(username=username).exists():
            raise forms.ValidationError('A user with this username already exist')
        return username

    def clean_email(self):
        # Check that email is not used already
        email = self.cleaned_data.get('email')
        if user_model.objects.filter(email=email).exists():
            raise forms.ValidationError('A user with this email already exist')
        return email


class MoveProjectForm(forms.Form):
    project = forms.ModelChoiceField(
        label='Choose a Project to move',
        queryset=Project.objects.all().order_by('org__name', 'name'),
        required=True
    )
    new_org = forms.ModelChoiceField(
        label='Destination Organization',
        queryset=Org.objects.all().order_by('name'),
        required=True
    )

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-default submit'))

        super(MoveProjectForm, self).__init__(*args, **kwargs)


class MoveProjectConfirmForm(forms.Form):

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<div><h4>Moving project: <span style="color:red">{{project.name }}</span></h4> '
                 '<h4>belonging to organization: <span style="color:red">{{project.org}} </span></h4></div>'),
            HTML('<h4 style="color:blue"><i class="fa fa-info" aria-hidden="true"></i> The following data will be moved:</h4>'),
            HTML('<div>'),
            HTML('<h5>Devices :</h5>'),
            HTML('<ul>{% for device_slug, ds in device_stream.items %}'
                 '<li><h6>{{ device_slug }}</h6><p> Streams: </p><ul>{% for s in ds %}<li>{{ s.slug }}</li>{% endfor %}</ul></li>'
                 '{% endfor %}</ul>'),
            HTML('<h5>Stream variables</h5>'),
            HTML('<ul>{% for sv in variables %}<li>{{ sv.slug }}</li>{% endfor %}</ul>'),
            HTML('<p style="color:red">'),
            HTML('  <i class="fa fa-exclamation-triangle" aria-hidden="true"></i>'),
            HTML('</p>'),
            HTML('</div>')
        )
        self.helper.add_input(Submit('submit', 'Yes, I know what I am doing', css_class='btn btn-danger btn-block submit'))

        super(MoveProjectConfirmForm, self).__init__(*args, **kwargs)


class DeleteProjectForm(forms.Form):
    project = forms.ModelChoiceField(
        label='Choose a project to delete',
        queryset=Project.objects.all().order_by('org__name', 'name'),
        required=True
    )

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-default submit'))

        super(DeleteProjectForm, self).__init__(*args, **kwargs)


class DeleteProjectConfirmForm(forms.Form):

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<div><h4>Deleting project: <span style="color:red">{{project.name }}</span></h4> '
                 '<h4>belonging to organization: <span style="color:red">{{project.org}} </span></h4></div>'),
            HTML('<h4 style="color:blue"><i class="fa fa-info" aria-hidden="true"></i> The following data will be deleted:</h4>'),
            HTML('<div>'),
            HTML('<h5>Devices :</h5>'),
            HTML('<ul>{% for device_slug, ds in device_stream.items %}'
                 '<li><h6>{{ device_slug }}</h6><p> Streams: </p><ul>{% for s in ds %}<li>{{ s.slug }}</li>{% endfor %}</ul></li>'
                 '{% endfor %}</ul>'),
            HTML('<h5>Stream variables</h5>'),
            HTML('<ul>{% for sv in variables %}<li>{{ sv.slug }}</li>{% endfor %}</ul>'),
            HTML('<p style="color:red">'),
            HTML('  <i class="fa fa-exclamation-triangle" aria-hidden="true"></i>'),
            HTML('  Project data, once deleted, CANNOT be recovered.'),
            HTML('</p>'),
            HTML('</div>')
        )
        self.helper.add_input(Submit('submit', 'Yes, I know what I am doing', css_class='btn btn-danger btn-block submit'))

        super(DeleteProjectConfirmForm, self).__init__(*args, **kwargs)


class DeviceBatchForm(forms.Form):
    template = forms.ModelChoiceField(
        label='Device Template',
        queryset=DeviceTemplate.objects.all().order_by('external_sku'),
        required=True
    )
    sg = forms.ModelChoiceField(
        label='Sensor Graph',
        queryset=SensorGraph.objects.filter(active=True).order_by('name'),
        required=True
    )
    name_format = forms.CharField(label='Name', max_length=100, required=True,)
    num_devices = forms.IntegerField(label='Number of Devices', min_value=1, required=True)

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<br>'),
            Div(
                Div('template', css_class='col-xs-6'),
                Div('sg', css_class='col-xs-6'),
                css_class='row'
            ),
            Div(
                Div(Field('name_format', placeholder=DEFAULT_IOTILE_DEVICE_NAME_FORMAT), css_class='col-xs-8'),
                Div('num_devices', css_class='col-xs-4'),
                css_class='row'
            ),
            HTML('<p>{id} most be included somewhere in the string. It will be replaced by the device ID</p>'),
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Create', css_class='btn btn-default submit'))

        super(DeviceBatchForm, self).__init__(*args, **kwargs)
        self.initial['name_format'] = DEFAULT_IOTILE_DEVICE_NAME_FORMAT
        self.initial['num_devices'] = 1

    def clean_name_format(self):
        # Check that username is not used already
        name_format = self.cleaned_data.get('name_format')
        if '{id}' not in name_format:
            raise forms.ValidationError('You must use {id} somewhere in the name')
        return name_format


class BatchUpgradeSgForm(forms.Form):
    sg_from = forms.ModelChoiceField(
        label='From: ',
        queryset=SensorGraph.objects.all().order_by('name'),
        required=True
    )
    sg_to = forms.ModelChoiceField(
        label='To: ',
        queryset=SensorGraph.objects.filter(active=True).order_by('name'),
        required=True
    )

    def __init__(self, *arg, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-default submit'))
        super(BatchUpgradeSgForm, self).__init__(*arg, **kwargs)


class BatchUpgradeSgConfirmForm(forms.Form):

    def __init__(self, *arg, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Confirm', css_class='btn btn-danger btn-block submit'))
        self.helper.layout = Layout(
            HTML('<h3 style="color:blue"><i class="fa fa-info" aria-hidden="true"></i> This is a dangerous operation. Be careful</h3>'
                 '<h3>{% if total > 1 %}The {{total}} devices {% else %} The device {% endif %} listed bellow will be upgraded</h3>'
                 '<h3>from sensor graph <span style="color:red">{{sg_from}}</span> to <span style="color:red">{{sg_to}}</span></h3>'
                 '{%if total > 0 %}'
                 '<table class="table table-striped">'
                 '<thead>'
                 '<tr><th>Label</th><th>Slug</th><th>Project</th><th>Organization</th></tr>'
                 '</thead>'
                 '<tbody>'
                 '{%for d in devices %}'
                 '<tr> <td>{{d.label}}</td><td>{{d.slug}}</td><td>{{d.project}}</td><td>{{d.org}}</td> </tr>'
                 '{% endfor %}'
                 '</tbody>'
                 '</table>'
                 '{% else %}'
                 '<h4>No device found</h4>'
                 '{% endif %}'),
        )
        super(BatchUpgradeSgConfirmForm, self).__init__(*arg, **kwargs)


class TestEmailForm(forms.Form):
    email = forms.EmailField(label='Email', max_length=100, required=True)

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML("<h4>Use this form to send a test email</h4>"),
            HTML('<br>'),
            'email',
        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))

        super(TestEmailForm, self).__init__(*args, **kwargs)


class GetDeviceForm(forms.Form):
    device_id = forms.CharField(label='Global Device ID', max_length=38, required=True)

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            FieldWithButtons('device_id', Submit('search', 'GO!', css_class='btn btn-success btn-block', )),
            HTML('<p> *Use regular integers (e.g. "10") or hex format (e.g. "0xa")</p>'),
            HTML('<br>')
        )

        super(GetDeviceForm, self).__init__(*args, **kwargs)

    def _parse_int(self, value):
        try:
            result = int(value)
        except ValueError:
            try:
                result = int(value, 16)
            except ValueError:
                raise forms.ValidationError('Only <int> (10) or <hex> (0xa) format accepted')
        return result

    def clean_device_id(self):
        # Check that device exists
        raw_id = self.cleaned_data.get('device_id')
        device_id = self._parse_int(raw_id)
        try:
            device = Device.objects.get(pk=device_id)
        except Device.DoesNotExist:
            raise forms.ValidationError('Device not found')

        return device


class DeviceSemiClaimConfirmForm(ModelForm):
    dst_org = forms.ModelChoiceField(
        label='Claim into Org:',
        queryset=Org.objects.all().order_by('name'),
        required=True
    )

    class Meta:
        model = Device
        fields = ['dst_org']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<p><b>Device {{ device.slug }} ({{ device.template }}) with sensor graph \'{{ device.sg }}\' </b></p>'),
            HTML('<hr>'),
            HTML('<h3 style="color:blue"><i class="fa fa-info" aria-hidden="true"></i> Make sure you understand the Claim Process</h3>'),
            HTML('<p>Semi-claiming a Device is required before it can be synced into an ArchFX Cloud</p>'),
            HTML('<br>'),
            'dst_org',
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Yes, I know what I am doing', css_class='btn btn-danger btn-block submit'))

        super().__init__(*args, **kwargs)


class DeviceClaimConfirmForm(ModelForm):
    dst_project = forms.ModelChoiceField(
        label='Claim into project:',
        queryset=Project.objects.all().order_by('org__name', 'name'),
        required=True
    )
    claimed_by = forms.ModelChoiceField(
        label='Claim it as (best to claim with Arch support account): ',
        queryset=user_model.objects.all().order_by('username'),
        required=True
    )
    state = forms.ChoiceField(
        label='Claim and set state to: ',
        help_text='Set to Inactive for shipping trackers',
        choices=DEVICE_STATE_CHOICES,
        required=True
    )

    class Meta:
        model = Device
        fields = ['dst_project', 'state', 'claimed_by']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<p><b>Device {{ device.slug }} ({{ device.template }}) with sensor graph \'{{ device.sg }}\' </b></p>'),
            HTML('<hr>'),
            HTML('<h3 style="color:blue"><i class="fa fa-info" aria-hidden="true"></i> Make sure you understand the Claim Process</h3>'),
            HTML('<p>Make sure you have selected the proper SensorGraph and DeviceTemplate</p>'),
            HTML('<p>Also make sure you are NOT claiming into a project with existing conflicting variables</p>'),
            HTML('<br>'),
            'dst_project',
            HTML('<p>Device is {}semi-claimed{}</p>'.format(
                '' if kwargs['instance'] and kwargs['instance'].org else 'NOT ',
                f" into the \'{kwargs['instance'].org.name}\' org" if kwargs['instance'] and kwargs['instance'].org else ' into an org',
            )),
            'state',
            'claimed_by',
            HTML('</p>'),
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Yes, I know what I am doing', css_class='btn btn-danger btn-block submit'))

        super(DeviceClaimConfirmForm, self).__init__(*args, **kwargs)
        if kwargs['instance']:
            # If device is already semi-claimed, only show projects from that org
            org = kwargs['instance'].org
            if org is not None:
                self.fields['dst_project'].queryset = Project.objects.filter(org=org).order_by('name')


class DeviceUnclaimConfirmForm(ModelForm):
    clean_streams = forms.BooleanField(label='Delete existing Stream and Stream Data?', required=False)

    class Meta:
        model = Device
        fields = ['clean_streams']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<p><b>Device {{ device.slug }} is labeled "{{ device.label }}" and belongs to project:</b></p>'),
            HTML('<h3>"{{ device.project }}"</h3>'),
            HTML('<h4>{{ properties }} Device properties will be deleted.</h4>'),
            HTML('<br><hr>'),
            HTML('<h3 style="color:blue"><i class="fa fa-info" aria-hidden="true"></i> This is a dangerous operation. Be careful</h3>'),
            HTML('<p>Be very sure this is not a customer device and if it is, that the customer has explicitly asked for this to happen</p>'),
            HTML('<br>'),
            'clean_streams',
            HTML('<p style="color:red">'),
            HTML('  <i class="fa fa-exclamation-triangle" aria-hidden="true"></i>'),
            HTML('  Stream data, once deleted, CANNOT be recovered.'),
            HTML('</p>'),
            HTML('<p style="color:red">'),
            HTML('  <i class="fa fa-exclamation-triangle" aria-hidden="true"></i>'),
            HTML('  You may be deleting CRITICAL customer information.'),
            HTML('  If you are not sure, leave the data. This allows you to reclaim the device and get data back. '),
            HTML('</p>'),
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Yes, I know what I am doing', css_class='btn btn-danger btn-block submit'))

        super(DeviceUnclaimConfirmForm, self).__init__(*args, **kwargs)


class UpgradeDeviceConfigForm(ModelForm):

    class Meta:
        model = Device
        fields = ['sg', 'template', 'label', 'external_id', 'state']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Upgrade configuration', css_class='btn btn-danger btn-block submit'))
        self.helper.layout = Layout(
            HTML('<h3 style="color:blue"><i class="fa fa-info" aria-hidden="true"></i> This is a dangerous operation. Be careful</h3>'),
            Div(
                Div('label', css_class='col-sm-8'),
                Div('external_id', css_class='col-sm-4'),
                css_class='row'
            ),
            'sg',
            'template',
            'state',
            HTML('<br>')
        )
        super(UpgradeDeviceConfigForm, self).__init__(*args, **kwargs)
        self.fields['sg'].queryset = SensorGraph.objects.filter(active=True).order_by('name')
        q = Q(active=True)
        if kwargs['instance']:
            q = q | Q(pk=kwargs['instance'].template.id)
        self.fields['template'].queryset = DeviceTemplate.objects.filter(q).order_by('external_sku')


class StaffStreamDataDeleteConfirmForm(ModelForm):
    class Meta:
        model = StreamId
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<h2>Stream slug: {{stream_slug}}</h2><br>'),
            HTML('{% if from_parse_iso %}<h2>{% if to_parse_iso %}Start date{%else%}Delete all data from{%endif%}'
                 ' {{from_parse_iso}}</h2>{% endif%}'),
            HTML('{% if to_parse_iso %}<h2>{% if from_parse_iso %}End date{%else%}Delete all data up to{%endif%}'
                 ' {{to_parse_iso}}</h2>{%endif%}'),
            HTML('{% if not from_parse_iso and not to_parse_iso %} <h2>All data will be deleted !</h2>{%endif%}'),
            HTML('{% if all %} <h2 style="color:red;">ATTENTION : This confirmation will also delete the stream itself !</h2>{%endif%}'),
            HTML('<br>'),
            ButtonHolder(
                Submit('submit', 'Confirm delete', css_class='btn btn-danger submit'),
            ),
            HTML(
                '{% if data_count > 0 %}'
                '<br>'
                '<h2> The following data will be deleted: </h2>'
                '<table class="table table-striped">'
                '<thead>'
                '<tr><th>Timestamps</th><th>SEQID</th><th>Value</th>'
                '</thead>'
                '<tbody>'
                '{%for d in data_qs %}'
                '<tr><td>{{d.timestamp.isoformat}}</td><td>{{d.incremental_id}}</td><td>{{d.value}}</td></tr>'
                '{% endfor %}'
                '{%for e in event_qs %}'
                '<tr><td>{{e.timestamp.isoformat}}</td><td>{{e.incremental_id}}</td><td>N/A</td></tr>'
                '{% endfor %}'
                '</tbody>'
                '</table>'
                '{% endif %}'
                '<br>')
        )
        super(StaffStreamDataDeleteConfirmForm, self).__init__(*args, **kwargs)


class StaffStreamDataDeleteForm(ModelForm):
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
                Submit('delete_data', 'Submit', css_class='btn-block btn-success submit'),
                HTML('{% if has_streamid %} <input type="submit" name="delete_all" value="Delete all stream data/event and the stream itself" class="btn btn-primary btn-block btn-danger submit submitButton"> {%endif%}')
            ),
        )
        super(StaffStreamDataDeleteForm, self).__init__(*args, **kwargs)

    def clean(self):
        if self.cleaned_data.get('date_from') and self.cleaned_data.get('date_to') and self.cleaned_data.get('date_from') > self.cleaned_data.get('date_to'):
            raise forms.ValidationError("The start date must be before the end date")
        return self.cleaned_data


class PingWorkerForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Ping Worker Now', css_class='btn btn-block btn-success submit'))

        super(PingWorkerForm, self).__init__(*args, **kwargs)


class DeviceHealthForm(ModelForm):

    CHOICES = (("", ""), (900, "15 minutes"), (1800, "30 minutes"), (2700, "45 minutes"), (3600, "1 hour"),
               (7200, "2 hours"), (21600, "6 hours"), (43200, "12 hours"), (86400, "1 day"))

    new_period = forms.ChoiceField(choices=CHOICES, required=False, label="Set a new health check period: ")

    # NOTIFICATION_RECIPIENT_CHOICES = (('admin', 'Admins of the organization'),
    #                                   ('org', 'All members of the organization'),
    #                                   ('user', 'Only me'))
    # NOTIFICATION_RECIPIENT_CHOICES_STAFF = (('admin', 'Admins of the organization'),
    #                                         ('org', 'All members of the organization'),
    #                                         ('user', 'Only me'), ('staff', 'Arch staff'))

    # notification_recipient = forms.ChoiceField(label='Notification Recipients', choices=NOTIFICATION_RECIPIENT_CHOICES, required=True)
    emails = SimpleArrayField(forms.CharField(max_length=2048), label='Recipient emails (emails are separated by commas ",")',
                              required=False, help_text="Left blank if you don't want to change the current recipients")

    class Meta:
        model = Device
        fields = []

    def __init__(self, user, *args, **kwargs):
        enabled = kwargs.pop('enabled')
        super(DeviceHealthForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<h2>Device slug: {{object.slug}}</h2><br>'),
            Submit('enable_check', 'Enable Health Check', css_class='btn btn-block btn-success hidden' if enabled else 'btn btn-block btn-success'),
            Div(HTML('<h2>Status: {{device_health.health_status}}</h2>'
                     '<h2>Last heartbeat: {{device_health.last_heartbeat_dt}}</h2>'
                     '<h2>Current check period: {{device_health.health_check_period}}</h2>'
                     '<h2>Current notification recipients: {{device_health.notification_recipient}}</h2>'
                     '<br>'), css_class="" if enabled else "hidden"),
            Field('new_period', css_class='select form-control', type="" if enabled else "hidden"),
            # Field('notification_recipient', css_class='select form-control', type="" if enabled else "hidden"),
            Field('emails', type="" if enabled else "hidden"),
            Submit('update', 'Update health check settings', css_class='btn btn-block btn-default' if enabled else 'btn btn-block btn-default hidden'),
            Submit('disable_check', 'Disable Health Check', css_class='btn btn-block btn-danger' if enabled else 'btn btn-block btn-danger hidden'),
        )

    def clean(self):
        data = self.cleaned_data
        data['notification_recipient'] = None
        if 'emails' in data and data['emails']:
            emails = data['emails']
            for e in emails:
                try:
                    validate_email(e)
                except ValidationError:
                    raise forms.ValidationError("The emails you entered are not valid")
            notification_recipient = {"emails": emails}
            data['notification_recipient'] = notification_recipient
        return data


class CheckDataTimeForm(forms.Form):

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Submit('submit', 'Submit Test data point', css_class='btn-block btn-success submit'),
            HTML('<br>'),
            Submit('refresh', 'Refresh', css_class='btn-block btn-success submit')
        )
        super(CheckDataTimeForm, self).__init__(*args, **kwargs)


class MoveDeviceDataForm(forms.Form):
    dev0 = forms.CharField(label='Device ID (From)', max_length=38, required=True)
    dev1 = forms.CharField(label='Device ID (To)', max_length=38, required=True)
    start = forms.DateTimeField(required=False, label='Start date: (optional)', help_text='Format: YYYY-MM-DD HH:MM:SS *in your local time')
    end = forms.DateTimeField(required=False, label='End date: (optional)', help_text='Format: YYYY-MM-DD HH:MM:SS *in your local time')

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<b>This will move all StreamData from one device to another</b>'),
            HTML('<b>Current restriction requires both devices to be part of the same project</b>'),
            Div(
                Div('dev0', css_class='col-xs-6'),
                Div('dev1', css_class='col-xs-6'),
                css_class='row'
            ),
            HTML('<p> *Use regular integers (e.g. "10") or hex format (e.g. "0xa")</p>'),
            HTML('<br>'),
            HTML('<h5>Select the optional start and end dates to transfer</h5>'),
            Div(
                Div('start', css_class='col-xs-6'),
                Div('end', css_class='col-xs-6'),
                css_class='row'
            ),
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-default submit'))

        super(MoveDeviceDataForm, self).__init__(*args, **kwargs)

    def _parse_int(self, value):
        try:
            result = int(value)
        except ValueError:
            try:
                result = int(value, 16)
            except ValueError:
                raise forms.ValidationError('Only <int> (10) or <hex> (0xa) format accepted')
        return result

    def clean_dev0(self):
        # Check that username is not used already
        raw_id = self.cleaned_data.get('dev0')
        device_id = self._parse_int(raw_id)
        try:
            device = Device.objects.get(pk=device_id)
        except Device.DoesNotExist:
            raise forms.ValidationError('Device not found')

        return device

    def clean_dev1(self):
        # Check that username is not used already
        raw_id = self.cleaned_data.get('dev1')
        device_id = self._parse_int(raw_id)
        try:
            device = Device.objects.get(pk=device_id)
        except Device.DoesNotExist:
            raise forms.ValidationError('Device not found')

        return device

    def clean(self):
        data = self.cleaned_data
        dev0 = data['dev0']
        dev1 = data['dev1']
        if dev0.project != dev1.project:
            raise forms.ValidationError("Both devices must be part of the same project")
        return data


class MoveDeviceDataConfirmForm(forms.Form):

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<div><h4>Moving data from device : <span style="color:red">{{dev0.slug }}</span> to device: <span style="color:red">{{dev1.slug}}</span></h4> '),
            HTML('{% if start or end %}<h5>  Data{% if start %} from {{start}}{% endif %}{% if end %} to {{end}}{% endif %}</h5>{%endif%}'),
            HTML('<h4 style="color:blue"><i class="fa fa-info" aria-hidden="true"></i> The following data will be moved:</h4>'),
            HTML('<div>'),
            HTML('<h5>Streams to move:</h5>'),
            HTML('<ul>{% for device_slug, ds in device_stream.items %}'
                 '<li><h6>From {{ device_slug }}</h6><ul>{% for s in ds %}<li>{{ s.slug }}</li>{% endfor %}</ul></li>'
                 '{% endfor %}</ul>'),
            HTML('<p style="color:red">'),
            HTML(' Double check everything twice <i class="fa fa-exclamation-triangle" aria-hidden="true"></i>'),
            HTML('</p>'),
            HTML('</div>')
        )
        self.helper.add_input(Submit('submit', 'Yes, I know what I am doing', css_class='btn btn-danger btn-block submit'))

        super(MoveDeviceDataConfirmForm, self).__init__(*args, **kwargs)


class DeviceResetKeysConfirmForm(ModelForm):
    class Meta:
        model = Device
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<p><b>Device {{ device.slug }} (DT: {{ device.template }}) has SensorGraph "{{ device.sg }}"</b></p>'),
            HTML('{% if device.project %}<h2 style="color:red">This deviced is claimed!!! Project: "{{ device.project }}"</h2>{% endif %}'),
            HTML('<br><hr>'),
            HTML('<h2>Device has {{ keys.count }} device keys:</h2>'),
            HTML('<br>'),
            HTML('<ol>'),
            HTML('{% for key in keys %}<li>Key type: {{ key.type }}</li>{% endfor %}'),
            HTML('</ol>'),
            HTML('<hr>'),
            HTML('<h3 style="color:blue"><i class="fa fa-info" aria-hidden="true"></i> This is a dangerous operation. Be careful</h3>'),
            HTML('<p>Be very sure this is not a customer device and if it is, that the customer has explicitly asked for this to happen</p>'),
            HTML('<p>Any keys stored on the device will no longer work</p>'),
            HTML('<p style="color:red">'),
            HTML('  <i class="fa fa-exclamation-triangle" aria-hidden="true"></i>'),
            HTML('  You may be deleting CRITICAL customer information.'),
            HTML('  If you are not sure, leave the data. This allows you to reclaim the device and get data back. '),
            HTML('</p>'),
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Yes, I know what I am doing', css_class='btn btn-danger btn-block submit'))

        super(DeviceResetKeysConfirmForm, self).__init__(*args, **kwargs)


class CacheSearchForm(forms.Form):
    q = forms.CharField()

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'get'

        self.helper.layout = Layout(
            FieldWithButtons('q', Submit('search', 'key', css_class='btn btn-success btn-block',))
        )

        super(CacheSearchForm, self).__init__(*args, **kwargs)


class SmsSendForm(forms.Form):
    phone_number = forms.RegexField(regex=r'^\+?1?\d{9,15}$',
                                    help_text='Expected format: \'+999999999\'. Up to 15 digits allowed.',
                                    error_messages={
                                        'required': 'Expected format: \'+999999999\'. Up to 15 digits allowed.'
                                    })
    msg = forms.CharField(
        label="Short message",
        required=True,
        widget=forms.Textarea
    )

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<div><h4>Test SMS Send Infrastructure : <span style="color:red">Using {{from_number}}</span></h4> '),
            'phone_number',
            'msg',
            HTML('<br>')
        )
        self.helper.add_input(Submit('submit', 'Send', css_class='btn btn-success btn-block submit'))

        super(SmsSendForm, self).__init__(*args, **kwargs)


class BatchUpgradeDeviceTemplateForm(forms.Form):
    dt_from = forms.ModelChoiceField(
        label='From: ',
        queryset=DeviceTemplate.objects.all().order_by('external_sku'),
        required=True
    )
    dt_to = forms.ModelChoiceField(
        label='To: ',
        queryset=DeviceTemplate.objects.filter(active=True).order_by('external_sku'),
        required=True
    )

    def __init__(self, *arg, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-default submit'))
        super(BatchUpgradeDeviceTemplateForm, self).__init__(*arg, **kwargs)


class BatchUpgradeDeviceTemplateConfirmForm(forms.Form):

    def __init__(self, *arg, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Confirm', css_class='btn btn-danger btn-block submit'))
        self.helper.layout = Layout(
            HTML('<h3 style="color:blue"><i class="fa fa-info" aria-hidden="true"></i> This is a dangerous operation. Be careful</h3>'
                 '<h3>{% if total > 1 %}The {{total}} devices {% else %} The device {% endif %} listed bellow will be upgraded</h3>'
                 '<h3>from Product <span style="color:red">{{dt_from}}</span> to <span style="color:red">{{dt_to}}</span></h3>'
                 '{%if total > 0 %}'
                 '<table class="table table-striped">'
                 '<thead>'
                 '<tr><th>Label</th><th>Slug</th><th>Project</th><th>Organization</th></tr>'
                 '</thead>'
                 '<tbody>'
                 '{%for d in devices %}'
                 '<tr> <td>{{d.label}}</td><td>{{d.slug}}</td><td>{{d.project}}</td><td>{{d.org}}</td> </tr>'
                 '{% endfor %}'
                 '</tbody>'
                 '</table>'
                 '{% else %}'
                 '<h4>No device found</h4>'
                 '{% endif %}'),
        )
        super(BatchUpgradeDeviceTemplateConfirmForm, self).__init__(*arg, **kwargs)


# class StreamTimeSeriesMigrateForm(forms.Form):
#     stream_id = forms.IntegerField(label='Stream ID', required=True)

#     def __init__(self, *args, **kwargs):
#         self.helper = FormHelper()
#         self.helper.form_method = 'post'
#         self.helper.layout = Layout(
#             HTML('<p>This will migrate a {{ old_model }} point to a {{ new_model }}.</p>'),
#             HTML('<p>(Copy the current object corresponding to the given primary ID to create a new object for the new model in the new database.)</p>'),
#             HTML('<br>'),
#             Field('stream_id', css_class='row', placeholder='Primary Key of the DB entry'),
#             HTML('<br>'),
#         )
#         self.helper.add_input(Submit('submit', 'Migrate', css_class='btn btn-success submit'))

#         super(StreamTimeSeriesMigrateForm, self).__init__(*args, **kwargs)
