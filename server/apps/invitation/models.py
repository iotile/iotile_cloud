import datetime
import uuid
import logging

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Q
from django.conf import settings
from django.urls import reverse
from django.contrib import messages
from django.db import migrations, transaction

from allauth.account.signals import user_signed_up

from apps.org.models import Org, OrgMembership
from apps.org.roles import DEFAULT_ROLE, ROLE_DISPLAY
from apps.emailutil.tasks import Email

INVITATION_ACTIVE_DAYS = 14 # two weeks
logger = logging.getLogger(__name__)


class InvitationManager(models.Manager):

    def create_invitation(self, email, sent_by, org):
        instance = self.model.objects.create(email=email, sent_by=sent_by, org=org)
        return instance

    def user_already_invited(self, email=None):
        return self.model.objects.active_invitations().filter(email__iexact=email, accepted=False).exist()

    def user_already_accepted(self, email=None):
        return self.model.objects.filter(email__iexact=email, accepted=True).exist()

    def expired_invitations(self, org=None):
        return self.filter(self.expired_invitations_qs(org))

    def active_invitations(self, org=None):
        return self.exclude(self.expired_invitations_qs(org))

    def pending_invitations(self, org=None):
        if org:
            return self.filter(accepted=False, org=org)
        return self.filter(accepted=False)

    def expired_invitations_qs(self, org=None):
        expired_window_qs = Q(sent_on__lt=timezone.now() - datetime.timedelta(days=INVITATION_ACTIVE_DAYS))
        q = Q(accepted=True) | expired_window_qs
        if org:
            q = q & Q(org=org)
        return q

    def delete_expired_invitations(self):
        self.expired_invitations().delete()


class Invitation(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(verbose_name=_('email address'))
    accepted = models.BooleanField(verbose_name=_('accepted'), default=False)

    sent_on = models.DateTimeField(verbose_name=_('sent on'), null=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name=_('sent by'), related_name='invitations'
    )
    org = models.ForeignKey(Org, on_delete=models.CASCADE, verbose_name=_('Company Name'), related_name='invitations')

    # Default Role to set members to. Default to regular member. See org/roles.py
    role = models.CharField('Permissions Role to set new user to', max_length=3, default=DEFAULT_ROLE)

    created_on = models.DateTimeField('created_on', auto_now_add=True)

    objects = InvitationManager()

    class Meta:
        ordering = ['org', 'email']
        unique_together = (('org', 'email'),)

    def __str__(self):
        return '{0}--{1}'.format(str(self.id), self.email)

    def has_expired(self):
        return timezone.now() > (self.sent_on + datetime.timedelta(days=INVITATION_ACTIVE_DAYS))

    def get_accept_url(self, request):
        url = reverse('org:invitation:accept', args=[self.org.slug, self.id])
        return request.build_absolute_uri(url)

    def send_email_notification(self, request):
        subject = _('Invitation to join {}'.format('iotile.cloud'))

        ctx = {
            'url': self.get_accept_url(request),
            'from_user': self.sent_by.username,
            'from_email': self.sent_by.email,
            'org_name': self.org.name
            }

        invite_email = Email()
        invite_email.send_email('invitation', subject, ctx, [self.email])

    def get_role_display(self):
        return ROLE_DISPLAY[self.role]


def check_for_new_user_invitations(sender, **kwargs):
    new_user = kwargs['user']
    request = kwargs['request']
    logger.info('A new user has signed up! - {username}'.format(username=new_user.username))
    logger.info('--> New User: ' + str(new_user))
    for key in request.session.keys():
        logger.info('session({0}) = {1}'.format(key, request.session[key]))
    if 'invitation_id' in request.session:
        # Check invitation
        invitation_id = request.session.get('invitation_id')
        try:
            invitation = Invitation.objects.get(pk=invitation_id)
            logger.info('Found Invitation: {0}'.format(invitation))
        except Invitation.DoesNotExist:
            logger.warning('Invitation ID not found. No membership created')
            messages.error(request, 'Invitation ID not found. No Org membership created')
            return

        # Create Membership
        if not invitation.accepted:
            with transaction.atomic():
                org = invitation.org
                org.register_user(new_user, role=invitation.role)
                invitation.accepted = True
                invitation.save()
            logger.info('New User added to {0}'.format(org))
        else:
            messages.warning(request, 'This invitation has already been accepted. Cannot add to Org')

        del request.session['invitation_id']
        request.session.modified = True



user_signed_up.connect(check_for_new_user_invitations)
