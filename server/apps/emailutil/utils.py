import json
import logging

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.org.models import Org, OrgMembership

user_model = get_user_model()
logger = logging.getLogger(__name__)


def get_member_choice_list_by_org(org):
    return [('user:{}'.format(u.slug), 'Member: {}'.format(u)) for u in Org.objects.members_qs(org).order_by('slug')]


class EmailRecipientHelper(object):

    def _check_email(self, qualifier, org):
        return [qualifier,]

    def _get_emails_for_user(self, qualifier, org):
        user = user_model.objects.filter(is_active=True, slug=qualifier).first()
        if user and org.has_access(user):
            return [user.email,]
        return []

    def _get_emails_for_org(self, qualifier, org):
        emails = []
        if qualifier == "admin":
            for member in OrgMembership.objects.filter(org=org, is_org_admin=True, is_active=True, user__is_active=True).select_related('user'):
                emails.append(member.user.email)
        elif qualifier == "all":
            for user in Org.objects.members_qs(org):
                if user.is_active:
                    emails.append(user.email)
        return emails

    def _get_emails_for_staff(self, qualifier, org):
        assert qualifier == 'all'
        emails = []
        for user in user_model.objects.filter(is_staff=True, is_active=True):
            emails.append(user.email)
        return emails

    def get_emails_from_recipient_list(self, recipients, org):
        """

        :param recipients: List of encoded recipient types. e.g. [user:david, org:admin, org:all, email:joe@test.com, staff:all]
        :param org: Org to check access. Only explicit emails (and staff) are excent from check
        :return: List of emails
        """

        factory = {
            'email': self._check_email,
            'user': self._get_emails_for_user,
            'org': self._get_emails_for_org,
            'staff': self._get_emails_for_staff,
        }

        email_set = set()
        for item in recipients:
            parts = item.split(':')
            if len(parts) == 2:
                type = parts[0]
                qualifier = parts[1]
                if type in factory:
                    email_list = factory[type](qualifier, org)
                    for email in email_list:
                        email_set.add(email)

        return list(email_set)
