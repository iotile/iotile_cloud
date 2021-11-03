import pytz
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Layout, Submit
from django import forms
from django.db.models import Q
from django.forms import ModelForm, SelectMultiple

from apps.streamnote.models import StreamNote
from apps.utils.aws.redshift import get_ts_from_redshift
from apps.utils.data_helpers.manager import DataManager
from apps.utils.data_mask.form_mixins import DataMaskFormMixin
from apps.utils.data_mask.mask_utils import get_data_mask_date_range
from apps.utils.iotile.variable import DATA_TRIM_EXCLUSION_LIST
from apps.utils.timezone_utils import str_to_dt_utc, str_utc

from .models import *
from .worker.device_data_trim import get_streams_to_trim

DATETIME_WIDGET_OPTIONS = {
    'format': 'dd/mm/yyyy HH:ii:ss',
    'autoclose': True
}


class DeviceForm(ModelForm):
    class Meta:
        model = Device
        fields = ['label']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))

        super(DeviceForm, self).__init__(*args, **kwargs)


class DeviceMoveForm(ModelForm):
    dst_project = forms.ModelChoiceField(
        label='New Project:',
        queryset=Project.objects.none(),
        required=True
    )
    move_data = forms.BooleanField(initial=True, required=False)
    class Meta:
        model = Device
        fields = []

    def __init__(self, project_qs, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'dst_project',
            HTML('<hr>'),
            HTML('<p>Select "Move Data" if you want to move all existing stream data to the new project.</p>'),
            HTML('<p>Otherwise, the data will be left on the existing project, and available if the device is moved back.</p>'),
            'move_data',
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))

        super(DeviceMoveForm, self).__init__(*args, **kwargs)
        self.fields['dst_project'].queryset = project_qs

    def clean_project(self):
        """Make sure project is selected"""
        project = self.cleaned_data.get('project')
        if project is None:
            raise forms.ValidationError("New Project (destination) most be selected")
        return project


class DeviceResetForm(ModelForm):
    class Meta:
        model = Device
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        if 'instance' in kwargs:
            device = kwargs['instance']

            note = """
            <div class="alert alert-warning alert-dismissible fade in" role="alert">
            This operation will remove all data records associated with device '{slug}'.<br>
            This operation will reset the device to when originally claimed and <b>cannot be undone</b>.
            </div>
            """.format(slug=device.slug)

            stream_slugs = [s.slug for s in device.streamids.filter(block__isnull=True)]
            data_count = DataManager.filter_qs('data', stream_slug__in=stream_slugs).count()
            event_count = DataManager.filter_qs('event', stream_slug__in=stream_slugs).count()
            note_count = StreamNote.objects.filter(target_slug=device.slug).count()
            note_count += StreamNote.objects.filter(target_slug__in=stream_slugs).count()

            table = """
            <table class="table table-striped table-bordered">
            <tr><th>Total data entries to delete</th><td>{data}</td></tr>
            <tr><th>Total events to delete</th><td>{events}</td></tr>
            <tr><th>Total notes to delete</th><td>{notes}</td></tr>
            <tr><th>Total number of properties to delete</th><td>{properties}</td></tr>
            </table>
            <p><b>
            An alternative of this operation is to create a <a href="{url}">Device Data Archive</a> which will 
            result in the same reset, but only after making a copy to archive.
            </b></p>
            """.format(streams=device.streamids.count(), data=data_count, properties=device.get_properties_qs().count(),
                       events=event_count, notes=note_count, url=device.get_create_archive_url())

        else:
            note = """
            <div class="alert alert-success alert-dismissible fade in" role="alert">
            This operation will remove all data records associated with the device.<br>
            This operation will reset the device to when originally claimed and <b>cannot be undone</b>.
            </div>
            """
            table = '<br>'

        self.helper.layout = Layout(
            HTML(note),
            HTML('<br>'),
            HTML(table),
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Reset Device', css_class='btn btn-block btn-danger submit'))

        super(DeviceResetForm, self).__init__(*args, **kwargs)


class DeviceTrimForm(ModelForm):
    start = forms.DateTimeField(required=False, label='Delete data before: (optional)',
                                help_text='Format: YYYY-MM-DD HH:MM:SS *in UTC time')
    '''
    start = forms.DateTimeField(required=False, label='Delete data before: (optional)',
                                    help_text='*in UTC time')
    '''
    end = forms.DateTimeField(required=False, label='Delete data after: (optional)',
                              help_text='Format: YYYY-MM-DD HH:MM:SS *in UTC time')

    class Meta:
        model = Device
        fields = []

    def __init__(self, start, end, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        if 'instance' in kwargs:
            device = kwargs['instance']

            stream_qs = get_streams_to_trim(device)
            stream_slugs = [s.slug for s in stream_qs]

            note = """
            <div class="alert alert-success alert-dismissible fade in" role="alert">
            This operation will trim data for device '{slug}'.<br>
            </div>
            """.format(slug=device.slug)

            alert = """
            <div class="alert alert-warning alert-dismissible fade in" role="alert">
            Select the start and end dates in UTC for all the data you would <b>like to keep</b> for this device.<br>
            Data outside of the selected time range will be <b>trimmed (permanently deleted).</b><br>
            You will get to review what data will be deleted before confirming.
            </div>
            """

            table = """
            <table class="table table-striped table-bordered">
            <head>
            <tr>
              <th>Variable</th>
              <th>Data Count</th>
              <th>Event Count</th>
              <th>Oldest</th>
              <th>Newest</th>
            </tr>
            </head>
            """

            data_count = event_count = 0
            for stream_slug in stream_slugs:
                ts0 = ts1 = None
                stream_data_qs = DataManager.filter_qs('data', stream_slug=stream_slug)
                stream_event_qs = DataManager.filter_qs('event', stream_slug=stream_slug)
                data0 = get_ts_from_redshift(stream_data_qs.first().timestamp) if stream_data_qs.count() else None
                data1 = get_ts_from_redshift(stream_data_qs.last().timestamp) if stream_data_qs.count() else None
                event0 = stream_event_qs.first().timestamp if stream_event_qs.count() else None
                event1 = stream_event_qs.last().timestamp if stream_event_qs.count() else None
                if data0 and event0:
                    ts0 = data0 if data0 > event0 else event0
                else:
                    if data0:
                        ts0 = data0
                    else:
                        ts0 = event0
                if data1 and event1:
                    ts1 = data1 if data1 > event1 else event1
                else:
                    if data1:
                        ts1 = data1
                    else:
                        ts1 = event1
                table += """
                <tr>
                  <th>{stream}</th>
                  <td>{data}</td>
                  <td>{event}</td>
                  <td>{first}</td>
                  <td>{last}</td>
                </tr>
                """.format(
                    stream=stream_slug.split('--')[-1],
                    data=stream_data_qs.count(),
                    event=stream_event_qs.count(),
                    first=str_utc(ts0) if ts0 else '',
                    last=str_utc(ts1) if ts1 else ''
                )
                data_count += stream_data_qs.count()
                event_count += stream_event_qs.count()

            table += """
            <tr>
              <th>Totals</th>
              <td>{data}</td>
              <td>{event}</td>
            </tr>
            """.format(
                data=data_count,
                event=event_count
            )

            table += '</table>'

        else:
            note = """
            <div class="alert alert-danger alert-dismissible fade in" role="alert">
            <b>ERROR</b>.
            </div>
            """
            alert = ""
            table = '<br>'
            table2 = '<br>'

        self.helper.layout = Layout(
            HTML('<br>'),
            HTML(note),
            HTML('<br>'),
            HTML(table),
            HTML('<br>'),
            HTML('<h4>Select the start and end dates for all the data to keep</h4>'),
            HTML('<br>'),
            HTML(alert),
            HTML('<br>'),
            Div(
                Div('start', css_class='col-sm-6 col-xs-12'),
                Div('end', css_class='col-sm-6 col-xs-12'),
                css_class='row'
            ),
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Delete Device Data outside range', css_class='btn btn-block btn-danger submit'))

        super(DeviceTrimForm, self).__init__(*args, **kwargs)
        if start:
            self.fields['start'].initial = str_to_dt_utc(start)
        if end:
            self.fields['end'].initial = str_to_dt_utc(end)

    def clean(self):
        if not (self.cleaned_data.get('start') or self.cleaned_data.get('end')):
            raise forms.ValidationError("Start and/or End should be specified")
        if self.cleaned_data.get('start') and self.cleaned_data.get('end') and self.cleaned_data.get('start') > self.cleaned_data.get('end'):
            raise forms.ValidationError("The start date must be before the end date")
        return self.cleaned_data

    def clean_start(self):
        """Force the value returned by the datetime widget to be a UTC (as I cannot figure out how to make the widget be UTC)"""
        start = self.cleaned_data.get('start')
        if start:
            utc_dt = start.replace(tzinfo=pytz.utc)
            utc_dt = utc_dt.replace(second=0, microsecond=0)
            logger.info('Cleaned Start timestamp: {}'.format(utc_dt))
            return utc_dt
        return None

    def clean_end(self):
        """Force the value returned by the datetime widget to be a UTC (as I cannot figure out how to make the widget be UTC)"""
        end = self.cleaned_data.get('end')
        if end:
            utc_dt = end.replace(tzinfo=pytz.utc)
            utc_dt = utc_dt.replace(second=0, microsecond=0)
            logger.info('Cleaned End timestamp: {}'.format(utc_dt))
            return utc_dt
        return None


class DeviceTrimConfirmForm(ModelForm):
    class Meta:
        model = Device
        fields = []

    def __init__(self, start, end, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Confirm Delete (Trim)', css_class='btn btn-block btn-danger submit'))
        super(DeviceTrimConfirmForm, self).__init__(*args, **kwargs)


class DeviceHealthForm(ModelForm):
    recipients = forms.MultipleChoiceField(
        label='Notification Recipients (Select from list)',
        help_text='Hold down "Control", or "Command" to select more than one.',
        widget=SelectMultiple(attrs={'size': '10'}),
        choices=[],
        required=True
    )
    extras = forms.CharField(
        label='Other emails (not members of the Organization)',
        required=False,
        help_text='One email address per row (e.g. joe@example.com)',
        widget=forms.Textarea
    )
    health_check_period = forms.IntegerField(
        label='Check every',
        help_text='Enter number in seconds',
        min_value=3600
    )

    class Meta:
        model = DeviceStatus
        fields = ['health_check_enabled', 'health_check_period']

    def __init__(self, org, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Save', css_class='btn btn-block btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h4>Device Health Notification Recipients</h4>'),
            HTML('<br>'),
            'health_check_enabled',
            'health_check_period',
            HTML('<br>'),
            'recipients',
            HTML('<br>'),
            'extras',
            HTML('<br>')
        )
        super(DeviceHealthForm, self).__init__(*args, **kwargs)
        choices = [
            ('org:admin', 'Organization Admins'),
            ('org:all', 'Organization Members')
        ]
        choices += [('user:{}'.format(u.slug), 'Member: {}'.format(u)) for u in Org.objects.members_qs(org).order_by('slug')]
        self.fields['recipients'].choices = choices
        self.fields['recipients'].initial = []
        extras = []
        for item in self.instance.notification_recipients:
            parts = item.split(':')
            if parts[0] == 'email':
                extras.append(parts[1])
            else:
                self.fields['recipients'].initial.append(item)
        if extras:
            self.fields['extras'].initial = '\n'.join(extras)


class DeviceFilterLogsClearForm(ModelForm):
    class Meta:
        model = Device
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<h4>Are you sure you want to clear filter logs?</h4>'),
            HTML('<br>')
        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))

        super(DeviceFilterLogsClearForm, self).__init__(*args, **kwargs)


class DeviceMaskForm(ModelForm, DataMaskFormMixin):
    start = forms.DateTimeField(required=False, label='Hide data before: (optional)',
                                help_text='Format: YYYY-MM-DD HH:MM:SS *in UTC time')
    end = forms.DateTimeField(required=False, label='Hide data after: (optional)',
                              help_text='Format: YYYY-MM-DD HH:MM:SS *in UTC time')
    """
    events = forms.CharField(
        required=False, label='List of event IDs to filter',
        help_text='comma-separated list of integers',
        widget=forms.Textarea
    )
    data = forms.CharField(
        required=False, label='List of data IDs to filter',
        help_text='comma-separated list of integers',
        widget=forms.Textarea
    )
    """

    class Meta:
        model = Device
        fields = []

    def __init__(self, start, end, event_list, data_list, *args, **kwargs):
        assert 'instance' in kwargs
        device = kwargs['instance']

        self.helper = self.setup_crispy_helper(device)
        super(DeviceMaskForm, self).__init__(*args, **kwargs)

        # Check for existing values, or forced values from parameter list (i.e. ?start=)
        mask_data = get_data_mask_date_range(device)
        if start:
            self.fields['start'].initial = str_to_dt_utc(start)
        elif mask_data and mask_data['start']:
            self.fields['start'].initial = str_to_dt_utc(mask_data['start'])
        if end:
            self.fields['end'].initial = str_to_dt_utc(end)
        elif mask_data and mask_data['end']:
            self.fields['end'].initial = str_to_dt_utc(mask_data['end'])
        """
        if event_list:
            event_list = event_list.replace(" ", "")
            self.fields['events'].initial = event_list
        if data_list:
            data_list = data_list.replace(" ", "")
            self.fields['data'].initial = data_list
        """

    def get_streams_to_mask(self, obj):
        """
        Get query set for valid streams to mask
        For example, we want to keep the trip start and trip ended around even after the trim

        :param obj: Device object
        :return: queryset
        """
        assert obj
        q = Q(lid__in=DATA_TRIM_EXCLUSION_LIST) | Q(app_only=True)
        var_exclude_qs = obj.project.variables.filter(q)
        stream_qs = obj.streamids.filter(block__isnull=True, device__isnull=False, project=obj.project)
        stream_qs = stream_qs.exclude(variable__in=var_exclude_qs)

        return stream_qs
