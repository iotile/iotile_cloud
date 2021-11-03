import pytz
import logging

from captcha.fields import ReCaptchaField

from django import forms as forms
from django.forms import ModelForm
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import ReadOnlyPasswordHashField

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, HTML

from allauth.account.forms import SignupForm, LoginForm, ResetPasswordForm, ResetPasswordKeyForm

from .models import Account

logger = logging.getLogger(__name__)


class TimeZoneFormField(forms.TypedChoiceField):
    def __init__(self, *args, **kwargs):

        def coerce_to_pytz(val):
            try:
                return pytz.timezone(val)
            except pytz.UnknownTimeZoneError:
                raise ValidationError("Unknown time zone: '%s'" % val)

        defaults = {
            'coerce': coerce_to_pytz,
            'choices': [(tz, tz) for tz in pytz.common_timezones],
            'empty_value': None,
        }
        defaults.update(kwargs)
        super(TimeZoneFormField, self).__init__(*args, **defaults)


class AccountUpdateForm(ModelForm):
    time_zone = TimeZoneFormField()
    class Meta:
        model = Account
        fields = ['username', 'name', 'tagline']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML("<h4>Avatars are currently supported via <a href=\"https://gravatar.com\" class=\"btn btn-default btn-sm\"><img src=\"https://en.gravatar.com/favicon.ico\" width=\"28\" title=\"Gravatar\"></a></h4>"),
            HTML('<br>'),
            'username',
            'name',
            'tagline',
            'time_zone'
        )
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))


        super(AccountUpdateForm, self).__init__(*args, **kwargs)
        tz = settings.TIME_ZONE
        if 'instance' in kwargs:
            user = kwargs['instance']
            if user and user.time_zone:
                tz = user.time_zone
        self.initial['time_zone'] = tz
        self.fields['username'].required = True

    def clean_username(self):
        # Check that the username does not have a space in it
        username = self.cleaned_data.get('username')
        if ' ' in username:
            raise forms.ValidationError("Username cannot have spaces")
        return username


class AllauthSignupForm(SignupForm):
    """Base form for django-allauth to use, adding a ReCaptcha function"""

    captcha = ReCaptchaField()
    name = forms.CharField(label='Full Name')

    def __init__(self, *args, **kwargs):
        super(AllauthSignupForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_show_labels = False
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field('username', placeholder='Username *'),
            Field('name', placeholder='Full Name *'),
            Field('email', placeholder='E-mail address *'),
            Field('password1', placeholder='Password *'),
            Field('password2', placeholder='Password (again) *'),
        )

    def clean_username(self):
        # Check that the username does not have a space in it
        username = self.cleaned_data.get('username').lower()
        if ' ' in username:
            raise forms.ValidationError("Username cannot have spaces")
        # Check username is not already used
        if Account.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Username is not available")
        return username


class AllauthLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super(AllauthLoginForm, self).__init__(*args, **kwargs)
        self.fields['password'].widget = forms.PasswordInput()

        self.helper = FormHelper()
        self.helper.form_show_labels = False
        self.helper.form_tag = False
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Field('login', placeholder='Email address'),
            Field('password', placeholder='Password'),
        )
        #self.helper.add_input(Submit('submit', 'Log in', css_class='btn btn-default submit'))


class AllauthResetPasswordForm(ResetPasswordForm):
    captcha = ReCaptchaField()

    def __init__(self, *args, **kwargs):
        super(AllauthResetPasswordForm, self).__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_show_labels = False
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field('email'),
        )


class AllauthResetPasswordKeyForm(ResetPasswordKeyForm):
    def __init__(self, *args, **kwargs):
        super(AllauthResetPasswordKeyForm, self).__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_show_labels = False
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field('password1'),
            Field('password2'),
        )


class AdminUserCreationForm(forms.ModelForm):
    """A form for creating new users. Includes all the required
    fields, plus a repeated password."""
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Password confirmation', widget=forms.PasswordInput)
    time_zone = TimeZoneFormField()

    class Meta:
        model = Account
        fields = ('username', 'email', 'name', 'time_zone',  'is_staff', )

    def clean_password2(self):
        # Check that the two password entries match
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords don't match")
        return password2

    def clean_username(self):
        # Check that the username does not have a space in it
        username = self.cleaned_data.get('username').lower()
        if ' ' in username:
            raise forms.ValidationError("Username cannot have spaces")
        # Check username is not already used
        if Account.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Username is not available")
        return username

    def save(self, commit=True):
        # Save the provided password in hashed format
        user = super(AdminUserCreationForm, self).save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user

    def __init__(self, *args, **kwargs):
        super(AdminUserCreationForm, self).__init__(*args, **kwargs)
        tz = settings.TIME_ZONE
        self.initial['time_zone'] = tz


class AdminUserChangeForm(forms.ModelForm):
    """A form for updating users. Includes all the fields on
    the user, but replaces the password field with admin's
    password hash display field.
    """
    password = ReadOnlyPasswordHashField()
    time_zone = TimeZoneFormField()

    class Meta:
        model = Account
        fields = ('username', 'email', 'password', 'name', 'time_zone', 'is_active', 'is_staff', 'is_admin')

    def clean_password(self):
        # Regardless of what the user provides, return the initial value.
        # This is done here, rather than on the field, because the
        # field does not have access to the initial value
        return self.initial["password"]

    def clean_username(self):
        # Check that the username does not have a space in it
        username = self.cleaned_data.get('username')
        if ' ' in username:
            raise forms.ValidationError("Username cannot have spaces")
        return username
