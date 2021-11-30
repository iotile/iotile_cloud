import logging

from django import forms
from django.forms import ModelForm
from django.template.defaultfilters import slugify

from crispy_forms.bootstrap import FieldWithButtons, StrictButton
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Layout, Submit

from .models import AuthAPIKey, Org, OrgMembership
from .roles import MEMBERSHIP_FORM_BEGIN, MEMBERSHIP_FORM_END, ORG_ROLE_CHOICES

logger = logging.getLogger(__name__)


class OrgCreateForm(ModelForm):
    class Meta:
        model = Org
        fields = ['name']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'

        self.helper.layout = Layout(
            'name',
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Create New Company', css_class='btn btn-success submit'))

        super(OrgCreateForm, self).__init__(*args, **kwargs)

    def clean_name(self):
        # Check that username is not used already
        name = self.cleaned_data.get('name')
        slug = slugify(name)
        if Org.objects.filter(slug=slug).exists():
            raise forms.ValidationError('Organization with this Company Name already exists: {}'.format(name))
        return name


class OrgEditForm(ModelForm):
    about = forms.CharField(label='Description', max_length=400, required=False,
                            widget=forms.Textarea(attrs={'rows': 5}))
    class Meta:
        model = Org
        fields = ['name', 'about']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'

        self.helper.layout = Layout(
            'name',
            'about',
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Save', css_class='btn btn-block btn-success submit'))

        super(OrgEditForm, self).__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data.get('name')
        # Check that username is not used already
        if self.instance:
            slug = slugify(name)
            qs = Org.objects.filter(slug=slug)
            if qs.count() == 1 and self.instance.id != qs.first().id:
                raise forms.ValidationError('Organization with this Company Name already exists: {}'.format(name))
        return name


class OrgMembershipForm(ModelForm):
    # Filter Staff and Develpment Roles
    role = forms.ChoiceField(label="Select Permission Role",
                             choices=ORG_ROLE_CHOICES[MEMBERSHIP_FORM_BEGIN:MEMBERSHIP_FORM_END],
                             required=True)
    class Meta:
        model = OrgMembership
        fields = ['is_active', 'role']

    def __init__(self, user, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'role',
            HTML('<hr>'),
            Div(
                Field('is_active',
                      data_toggle="toggle",
                      data_size="small",
                      data_on="Active",
                      data_off="Disabled",
                      data_onstyle='success',
                      data_offstyle='danger',
                      data_style='ios'),
                css_class='checkbox-label'
            ),
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Change', css_class='btn btn-success btn-block submit'))

        super(OrgMembershipForm, self).__init__(*args, **kwargs)

        if user.is_staff:
            self.fields['role'].choices = ORG_ROLE_CHOICES
        else:
            # User should only be able to change to a role below itself
            if self.instance:
                user_membership = self.instance.org.get_membership_obj(user)
                role_index = 0
                while ORG_ROLE_CHOICES[role_index][0] != user_membership.role:
                    role_index += 1
                self.fields['role'].choices = ORG_ROLE_CHOICES[role_index:MEMBERSHIP_FORM_END]

    def clean(self):
        role = self.cleaned_data.get('role')
        is_active = self.cleaned_data.get('is_active')
        if role == 'a0' and is_active is False:
            raise forms.ValidationError("Owner cannot be disabled. Please downgrade this user first.")
        if role != 'a0' and self.instance.org.is_owner(self.instance.user) \
                and self.instance.org.owner_count() < 2:
            raise forms.ValidationError("Cannot remove owner: organization must have an owner.")
        return self.cleaned_data


class OrgMembershipMessageForm(ModelForm):
    # Filter Staff and Develpment Roles
    role = forms.ChoiceField(label="Send message to members with role:",
                             choices=ORG_ROLE_CHOICES[MEMBERSHIP_FORM_BEGIN:MEMBERSHIP_FORM_END],
                             required=True)
    message = forms.CharField(label='Message', required=False,
                              widget=forms.Textarea(attrs={'rows': 10}))
    class Meta:
        model = Org
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'role',
            HTML('<hr>'),
            'message',
            HTML('<hr>'),
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Send', css_class='btn btn-success btn-block submit'))

        super(OrgMembershipMessageForm, self).__init__(*args, **kwargs)

        self.fields['role'].choices = self.fields['role'].choices + [('-', 'All Members')]


class OrgDomainAdminForm(ModelForm):
    default_role = forms.ChoiceField(label="Default Permission Role", choices=ORG_ROLE_CHOICES, required=True)

    def __init__(self, *args, **kwargs):
        super(OrgDomainAdminForm, self).__init__(*args, **kwargs)
        if self.instance.id:
            self.fields['default_role'] = forms.ChoiceField(choices=ORG_ROLE_CHOICES)


class OrgMembershipAdminForm(ModelForm):
    role = forms.ChoiceField(label="Permission Role", choices=ORG_ROLE_CHOICES, required=True)

    def __init__(self, *args, **kwargs):
        super(OrgMembershipAdminForm, self).__init__(*args, **kwargs)
        if self.instance.id:
            self.fields['role'].initial = self.instance.role


class DataBlockSearchForm(forms.Form):
    q = forms.CharField(required=False, label=(''),
                        widget=forms.TextInput(attrs={'type': 'search', 'autocomplete': 'off'}))
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            FieldWithButtons('q', StrictButton('Search', css_class='btn btn-success btn-block',))
        )

        super(DataBlockSearchForm, self).__init__(*args, **kwargs)


class OrgAPIKeyCreateForm(ModelForm):
    class Meta:
        model = AuthAPIKey
        # fields = ['name', 'expiry_date', 'revoked']
        exclude = ['id', 'org']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success btn-block submit'))

        super(OrgAPIKeyCreateForm, self).__init__(*args, **kwargs)
