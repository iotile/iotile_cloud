
from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.forms import ModelForm
from django.template.defaultfilters import slugify

from crispy_forms.bootstrap import FieldWithButtons
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Layout, Submit

from apps.org.models import Org
from apps.project.models import Project
from apps.projecttemplate.models import ProjectTemplate
from apps.staff.forms import GetDeviceForm

user_model = get_user_model()


class NewShippingOrgForm(ModelForm):
    short_name = forms.CharField(label='Short Name', max_length=15, required=False,
                                 help_text='Leave empty if no support account is needed')
    owner = forms.ChoiceField(
        label='Create organization as: ',
        help_text='For new organizations, choice to create new account',
        choices=[],
        required=True
    )

    class Meta:
        model = Org
        fields = ['short_name', 'name', 'owner',]

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'

        self.helper.layout = Layout(
            Div(
                Div('name', css_class='col-sm-8, col-xs-12'),
                Div('short_name', css_class='col-sm-4, col-xs-12'),
                css_class='row'
            ),
            'owner',
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Create New Company', css_class='btn btn-success submit'))

        super(NewShippingOrgForm, self).__init__(*args, **kwargs)
        self.fields['owner'].choices = [
            ('new', 'Create new support account'),
            ('user', 'Use my account as owner')
        ]

        users = user_model.objects.all().order_by('username')
        for user in users:
            self.fields['owner'].choices.append((user.slug, user.email))

    def clean_short_name(self):
        short_name = self.cleaned_data.get('short_name')
        # Check that username is not used already
        if self.instance:
            username = 'support-{}'.format(slugify(short_name))
            qs = user_model.objects.filter(username=username)
            if qs.exists():
                raise forms.ValidationError('Support account {} already exists'.format(username))
        return short_name


class NewShippingProjectForm(ModelForm):

    class Meta:
        model = Project
        fields = ['name', 'org']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success btn-block submit'))

        super(NewShippingProjectForm, self).__init__(*args, **kwargs)


class ShippingDeviceClaimForm(GetDeviceForm):
    project = forms.ModelChoiceField(
        label='Claim into shipping project:',
        queryset=Project.objects.filter(
            project_template__in=ProjectTemplate.objects.filter(name__contains='Shipping')
        ).order_by('org__name', 'name'),
        required=True
    )

    def __init__(self, *args, **kwargs):
        description = """
         <p>
         After checking that the device can be claimed, and is compatible with a Shipping App, 
         the device will be claimed and set to inactive.
         </p>
        """
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<h3 style="color:blue"><i class="fa fa-info" aria-hidden="true"></i> Make sure you understand the Claim Process</h3>'),
            HTML('<br>'),
            HTML(description),
            HTML('<br>'),
            'device_id',
            HTML('<p> *Use regular integers (e.g. "10") or hex format (e.g. "0xa")</p>'),
            'project',
            HTML('<br>')
        )
        self.helper.add_input(Submit('submit', 'Claim Device', css_class='btn btn-success btn-block submit'))

        super(GetDeviceForm, self).__init__(*args, **kwargs)


class ShippingDeviceTimestampFixForm(GetDeviceForm):

    def __init__(self, *args, **kwargs):
        description = """
         <p>
         If the device rebooted during or after the trip ended, it is possible
         that the workers were unable to fix up all timestamps correctly.
         </p>
         <p>
         This form will schedule a worker task to use the Start/End times recorded by the Phone
         to fix all data and event timestamps
         </p>
        """
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML(description),
            HTML('<br>'),
            'device_id',
            HTML('<p> *Use regular integers (e.g. "10") or hex format (e.g. "0xa")</p>'),
            HTML('<br>')
        )
        self.helper.add_input(Submit('submit', 'Schedule Fix', css_class='btn btn-success btn-block submit'))

        super(ShippingDeviceTimestampFixForm, self).__init__(*args, **kwargs)
