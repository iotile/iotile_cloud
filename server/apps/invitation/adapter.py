import logging
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.forms import ValidationError

from allauth.account.adapter import DefaultAccountAdapter

from .models import Invitation

logger = logging.getLogger(__name__)


class InvitationAdapter(DefaultAccountAdapter):

    error_messages = {
        'username_blacklisted': _('Username can not be used. Please use a different username.'),
        'username_taken': 'Username is already taken. Please use a differnt username',
        'too_many_login_attempts': _('Too many failed login attempts. Try again later.'),
        'email_taken': _("A user is already registered with this e-mail address."),
    }

    def stash_verified_email(self, request, email):
        logger.info('*** stash_verified_email')
        request.session['account_verified_email'] = email

    def unstash_verified_email(self, request):
        logger.info('*** unstash_verified_email')
        account_verified_email = request.session.get('account_verified_email')
        request.session['account_verified_email'] = None
        return account_verified_email

    def save_user(self, request, user, form, commit=False):
        logger.info('*** save_user')
        data = form.cleaned_data
        logger.info('Commit:' + str(commit))
        user.username = data['username']
        user.email = data['email']
        user.name = data['name']
        if 'password1' in data:
            user.set_password(data['password1'])
        else:
            user.set_unusable_password()
        self.populate_username(request, user)
        user.save()
        return user

    def clean_email(self, email):
        """
        Validates an email value.
        """
        if ' ' in email:
            raise ValidationError('Spaces are not allowed')
        
        email_parts = email.split('@')
        if len(email_parts) != 2:
            raise ValidationError('Illegal email format. Missing "@"')
        domain_parts = email_parts[-1].split('.')
        if len(domain_parts) < 2:
            raise ValidationError('Illegal email format. Expecting at least one "."')

        # Do not allow login from a set of domains that have been disallowed for security reasons
        # Any domain with .ru or any domains that we have detected registering in for no reason
        # and when the domain does not correspond to an obvious company
        if domain_parts[-1] == 'ru':
            raise ValidationError('Domain is not currently supported. Please contact help@archsys.io for assistance')
        if '.'.join(domain_parts[-2:]) in [
            'avalins.com',
            'enersets.com',
            'yandex.com',
            'efastes.com',
        ]:
            raise ValidationError('Domain is not currently supported. Please contact help@archsys.io for assistance')

        return email.lower()

    def clean_username(self, username, shallow=False):
        """
        Validates an username value.
        """
        if ' ' in username:
            raise ValidationError('Spaces are not allowed')

        return username.lower()

