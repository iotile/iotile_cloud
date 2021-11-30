from django import forms
from django.utils.translation import gettext_lazy as _

from allauth.account.models import EmailAddress
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Fieldset, Layout, Submit

from apps.org.roles import DEFAULT_ROLE, MEMBERSHIP_FORM_BEGIN, MEMBERSHIP_FORM_END, ORG_ROLE_CHOICES

from .models import Invitation


class InvitationForm(forms.ModelForm):
    _org = None

    email = forms.EmailField(label=_('E-mail'),
                             help_text=_('If sending to existing user, you must use the email on record for that account'),
                             required=True,
                             widget=forms.TextInput(attrs={"type": "email", "size": "30"}))
    role = forms.ChoiceField(label="Permission Role",
                             help_text=_('The new user will be assigned this role'),
                             choices=ORG_ROLE_CHOICES, required=True)

    class Meta:
        model = Invitation
        fields = ['email', 'role']

    def __init__(self, user, org, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))
        super(InvitationForm, self).__init__(*args, **kwargs)
        self._org = org
        if user.is_staff:
            self.fields['role'].choices = ORG_ROLE_CHOICES
        else:
            self.fields['role'].choices = ORG_ROLE_CHOICES[MEMBERSHIP_FORM_BEGIN:MEMBERSHIP_FORM_END]
        self.fields['role'].initial = DEFAULT_ROLE

    def clean_email(self):
        # Check that username is not used already
        email = self.cleaned_data.get('email')
        emails = EmailAddress.objects.filter(email=email)
        if emails.exists():
            assert (emails.count() == 1)
            email_address = emails.first()
            user = email_address.user
            if self._org.membership.filter(user=user).exists():
                raise forms.ValidationError('User with email {0} is already a member of Organization'.format(email))
        if Invitation.objects.filter(email=email, org=self._org).exists():
            raise forms.ValidationError('Invitation already exists for {}'.format(email))

        return email


class InvitationAcceptForm(forms.ModelForm):

    class Meta:
        model = Invitation
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<h2>Do you accept the invitation to join as a member (with "{{invitation.get_role_display}}" role) of {{ invitation.org.name }}?</h2>'),
            HTML('<h4>You were invited by @{{ invitation.sent_by.username }} ({{ invitation.sent_by.email }})</h4>'),
            HTML('<br>'),
            HTML('<br>'),
        )

        self.helper.add_input(Submit('submit', 'I accept', css_class='btn btn-success submit'))
        super(InvitationAcceptForm, self).__init__(*args, **kwargs)


class InvitationAdminCreateForm(forms.ModelForm):
    email = forms.EmailField(label=_("E-mail"),
                             required=True,
                             widget=forms.TextInput(attrs={"type": "email", "size": "30"}))
    role = forms.ChoiceField(label="Permission Role",
                             choices=ORG_ROLE_CHOICES, required=True)

    def __init__(self, *args, **kwargs):
        super(InvitationAdminCreateForm, self).__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        cleaned_data = super(InvitationAdminCreateForm, self).clean()
        email = cleaned_data.get('email')
        org = cleaned_data.get('org')
        sent_by = cleaned_data.get('sent_by')
        instance = Invitation.objects.create_invitation(email=email, sent_by=sent_by, org=org)
        instance.send_email_notification(self.request)
        super(InvitationAdminCreateForm, self).save(*args, **kwargs)
        return instance

    class Meta:
        model = Invitation
        fields = ('email', 'org', 'role')


class InvitationAdminEditForm(forms.ModelForm):

    class Meta:
        model = Invitation
        fields = '__all__'


class InvitationDeleteConfirmForm(forms.ModelForm):
    class Meta:
        model = Invitation
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Confirm delete', css_class='btn btn-danger submit'))
        self.helper.layout = Layout(
            HTML('<h2>Delete invitation to {{object.email}} ?</h2><br>')
        )
        super(InvitationDeleteConfirmForm, self).__init__(*args, **kwargs)


class InvitationResendForm(forms.ModelForm):
    class Meta:
        model = Invitation
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Send', css_class='btn btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h2>Resend invitation to {{object.email}} to join {{object.org}}?</h2><br>')
        )
        super(InvitationResendForm, self).__init__(*args, **kwargs)