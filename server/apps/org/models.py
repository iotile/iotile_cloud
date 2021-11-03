import uuid
import logging
from django.db import models
from django.conf import settings
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.db.models import Manager
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.db.models import Q

from rest_framework_api_key.models import AbstractAPIKey

from allauth.account.signals import email_confirmed

from apps.utils.gravatar import get_gravatar_thumbnail_url
from apps.s3images.models import S3Image
from apps.orgtemplate.models import OrgTemplate

from .roles import ORG_ROLE_PERMISSIONS, NO_PERMISSIONS_ROLE, ROLE_DISPLAY, DEFAULT_ROLE

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
user_model = get_user_model()
logger = logging.getLogger(__name__)


def get_default_membership_permissions():
    """
    Need callable function for JSON default to avoid postgres.E003 warning
    :return: OrgMembership.permission default
    """
    return dict(ORG_ROLE_PERMISSIONS['m1'])


class OrgManager(Manager):
    """
    Manager to help with Org and their membership
    """

    def create_org(self, name, created_by, about='', is_vendor=False, *args, **kwargs):
        org = self.model(
            name=name, about=about, created_by=created_by, is_vendor=is_vendor
        )
        for key in kwargs:
            assert hasattr(org, key)
            setattr(org, key, kwargs[key])

        org.save()

        # Automatically create membership for owner
        membership = OrgMembership(user=created_by, org=org, is_org_admin=True, role='a0',
                                   permissions=dict(ORG_ROLE_PERMISSIONS['a0']))
        membership.save()

        return org

    def user_orgs_qs(self, user, permission=None):
        if permission:
            membership = OrgMembership.objects.filter(
                user=user, is_active=True, permissions__contains={permission: True}
            ).values_list('org_id', flat=True)
        else:
            membership = OrgMembership.objects.filter(user=user, is_active=True).values_list('org_id', flat=True)
        return Org.objects.filter(id__in=membership)

    def user_orgs_ids(self, user, permission=None):
        if permission:
            return OrgMembership.objects.filter(
                user=user, is_active=True, permissions__contains={permission: True}
            ).values_list('org_id', flat=True)
        else:
            return OrgMembership.objects.filter(user=user, is_active=True).values_list('org_id', flat=True)

    def members_qs(self, org):
        membership = OrgMembership.objects.filter(org=org, is_active=True).values_list('user_id', flat=True)
        return user_model.objects.filter(id__in=membership, is_active=True)

    def members_count(self, org):
        return self.members_qs(org).count()

    def get_from_request(self, request):
        resolver_match = request.resolver_match
        if resolver_match:
            org_slug = None
            if 'org_slug' in resolver_match.kwargs:
                org_slug = resolver_match.kwargs['org_slug']
            elif 'slug' in resolver_match.kwargs:
                org_slug = resolver_match.kwargs['slug']

            if org_slug:
                # self.model.objects.get(slug=org_slug)
                org = get_object_or_404(self.model, slug=org_slug)
                if org.has_access(request.user):
                    return org

        return None


class Org(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField('Company Name', max_length=50, unique=True)
    slug = models.SlugField(max_length=60, unique=True)
    about = models.TextField(blank=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_orgs')

    users = models.ManyToManyField(AUTH_USER_MODEL, through='OrgMembership', blank=True)

    # is_vendor should be used for organization that own DeviceTemplates and/or Components
    # and operate as vendors/partners more than customers
    is_vendor = models.BooleanField(default=False)

    # Organization Images
    avatar = models.ForeignKey(S3Image, on_delete=models.CASCADE, related_name='orgs', null=True, blank=True)

    ot = models.ForeignKey(OrgTemplate, related_name='orgs', null=True, blank=True, on_delete=models.SET_NULL)

    objects = OrgManager()

    class Meta:
        ordering = ['name']
        verbose_name = _("Organization")
        verbose_name_plural = _("Organizations")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.slug = slugify(self.name)
        super(Org, self).save(*args, **kwargs)

    @property
    def obj_target_slug(self):
        return '^{0}'.format(self.slug)

    @property
    def domain_names(self):
        """List of verified domain names"""
        domains = []
        for domain in self.domains.filter(verified=True):
            domains.append(domain.name)

        return domains

    def get_absolute_url(self):
        if self.is_vendor:
            return reverse('vendor:home', args=(self.slug,))
        return reverse('org:detail', args=(self.slug,))

    def get_membership_url(self):
        return reverse('org:members', args=(self.slug,))

    def get_archive_list_url(self):
        return reverse('org:datablock:list', args=(self.slug,))

    def get_reports_url(self):
        return reverse('org:report:list', args=(self.slug,))

    def is_member(self, user):
        return self.membership.filter(user=user, is_active=True, user__is_active=True).exists()

    def is_admin(self, user):
        return self.membership.filter(user=user, is_active=True, is_org_admin=True, user__is_active=True).exists()

    def is_owner(self, user):
        return self.membership.filter(user=user, is_active=True, role='a0', user__is_active=True).exists()

    def member_count(self):
        return self.membership.filter(is_active=True, user__is_active=True).count()

    def owner_count(self):
        return self.membership.filter(is_active=True, role='a0', user__is_active=True).count()

    def get_membership_obj(self, user):
        return self.membership.get(org=self, user=user)

    def permissions(self, user):
        if user.is_staff:
            # If staff, just return staff permissions
            return ORG_ROLE_PERMISSIONS['s0']
        try:
            membership = self.membership.get(user=user, org=self, is_active=True)
        except OrgMembership.DoesNotExist:
            return NO_PERMISSIONS_ROLE

        return membership.permissions

    def has_permission(self, user, permission):
        if user.is_staff:
            # If staff, just return staff permissions
            return permission in ORG_ROLE_PERMISSIONS['s0'] and ORG_ROLE_PERMISSIONS['s0'][permission]

        return self.membership.filter(user=user, org=self, is_active=True, permissions__contains={permission: True}).exists()

    def has_multiple_permissions(self, user, permissions):
        if user.is_staff:
            # If staff, just return staff permissions
            for permission in permissions:
                if not permission in ORG_ROLE_PERMISSIONS['s0'] or not ORG_ROLE_PERMISSIONS['s0'][permission]:
                    return False
            return True

        q = Q(user=user, org=self, is_active=True)
        for permission in permissions:
            q = q & Q(permissions__contains={permission: True})

        return self.membership.filter(q).exists()

    def set_permission(self, user, permission, value):
        try:
            membership = self.membership.get(user=user, org=self, is_active=True)
        except OrgMembership.DoesNotExist:
            return False

        membership.permissions[permission] = value
        membership.save()

        return True

    def has_access(self, user):
        if user.is_staff and user.is_active:
            return True

        return self.is_member(user)

    def has_write_access(self, user):
        if user.is_staff:
            return True

        return self.has_permission(user, 'can_manage_org_and_projects')

    def register_user(self, user, is_admin=False, role='m1'):
        if not self.membership.filter(user=user).exists():
            membership = OrgMembership(user=user, org=self, is_org_admin=is_admin, is_active=True,
                                       role=role, permissions=dict(ORG_ROLE_PERMISSIONS[role]))
            membership.save()
        else:
            membership = self.membership.get(user=user)
            membership.permissions = dict(ORG_ROLE_PERMISSIONS[role])
            membership.role = role
            membership.save()
        return membership

    def de_register_user(self, user, delete_obj=False):
        if self.is_member(user):
            membership = OrgMembership.objects.get(user=user, org=self)
            if delete_obj:
                membership.delete()
            else:
                membership.is_active = False
                membership.permissions = dict(NO_PERMISSIONS_ROLE)
                membership.role = '00'
                membership.save()

    def get_avatar_thumbnail_url(self):
        if self.avatar:
            return self.avatar.thumbnail_url
        email = 'admin@{0}.com'.format(self.slug)
        return get_gravatar_thumbnail_url(email, 100)

    def get_avatar_tiny_url(self):
        if self.avatar:
            return self.avatar.tiny_url
        email = 'admin@{0}.com'.format(self.slug)
        return get_gravatar_thumbnail_url(email, 28)

    def get_email_list(self, admin_only=True):
        emails = []
        if admin_only:
            members = self.membership.filter(is_active=True, role__in=['a0', 'a1'])
        else:
            members = self.membership.filter(is_active=True)
        for member in members:
            if member.user.is_active:
                emails.append(member.user.email)
        return emails

    def get_first_owner(self):
        member = self.membership.filter(is_active=True, role='a0').order_by('created_on').first()
        if member:
            return member.user
        return self.created_by

    def get_webapp_url(self):
        """
        Get URL for specific org page in WebApp
        e.g.
        https://app-stage.iotile.cloud/#/org/arch-internal
        :return: Absolute URL including domain
        """
        domain = getattr(settings, 'WEBAPP_BASE_URL')
        return '{0}/#/org/{1}'.format(domain, str(self.slug))


class OrgMembership(models.Model):
    """
    Represents Organization membership.
    Assumes users can belong to multiple Organizations (something that may be overkill)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='membership')
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='membership')

    created_on = models.DateTimeField('created_on', auto_now_add=True)

    is_active = models.BooleanField('Status', default=True)
    is_org_admin = models.BooleanField(default=False)

    # Member roles and permissions
    # See permissions.py
    permissions = models.JSONField(null=True, blank=True, default=get_default_membership_permissions)
    # The role is mostly used for the UI
    role = models.CharField(max_length=3, default=DEFAULT_ROLE)

    class Meta:
        ordering = ['org', 'user']
        verbose_name = _("Organization member")
        verbose_name_plural = _("Organization members")
        unique_together = (('org', 'user'),)

    def __str__(self):
        return '@{0}--{1}'.format(self.user.username, self.org.slug)

    def get_edit_url(self):
        return reverse('org:member-edit', kwargs={'pk': str(self.id)})

    def get_role_display(self):
        return ROLE_DISPLAY[self.role]

    def get_role_icon(self):
        factory = {
            's0': 'fa fa-user-secret text-danger',
            'a0': 'fa fa-certificate text-danger',
            'a1': 'fa fa-circle text-warning',
            'm1': 'fa fa-user text-primary',
            'r1': 'fa fa-user-times',
            'd1': 'fa fa-puzzle-piece',
        }
        if self.role in factory:
            return factory[self.role]
        return 'fa-question'


class OrgDomain(models.Model):
    """
    Represents an Organization HTTP domain.
    If this optional record exist, users that register with an email using this domain
    get automatically added as members if the associated Organization
    """

    # Actual domain name. e.g. arch-iot.com, archsys.io
    name = models.CharField('Domain Name', max_length=50, unique=True)
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='domains')

    created_on = models.DateTimeField('created_on', auto_now_add=True)

    # Veriefied is set to True after an Arch Staff member verifies the domain
    # Before the domain is verified, this record will not have any effect
    verified = models.BooleanField(default=False)

    # Default Role to set members to. Default to regular member. See roles.py
    default_role = models.CharField(max_length=3, default=DEFAULT_ROLE)

    class Meta:
        ordering = ['org', 'name']
        verbose_name = _("Organization domain")
        verbose_name_plural = _("Organization domains")

    def __str__(self):
        return '{0}'.format(self.name)

    def process_new_user(self, user):
        org = self.org
        # Only process user if not already on the Org
        if not org.is_member(user):
            logger.info('Auto registering user {} to Org {}'.format(user, org))
            org.register_user(user, role=self.default_role)

    @classmethod
    def get_domain_from_email(cls, email):
        email_parts = email.split('@')
        if len(email_parts) == 2:
            domain_name = email_parts[1]
            try:
                return OrgDomain.objects.get(name=domain_name, verified=True)
            except OrgDomain.DoesNotExist:
                return None


class AuthAPIKey(AbstractAPIKey):
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="api_keys")

    class Meta(AbstractAPIKey.Meta):
        verbose_name = "Custom M2M API key"
        verbose_name_plural = "Custom M2M API keys"

    def is_valid_key(self):
        return not (self.revoked or self.has_expired)


def process_domain_on_email_confirmed(sender, **kwargs):
    email_address = kwargs['email_address']
    try:
        user = email_address.user
        if email_address.verified:
            org_domain = OrgDomain.get_domain_from_email(email_address.email)
            if org_domain:
                org_domain.process_new_user(user)
    except user_model.DoesNotExist:
        logger.warning('Confirmed email not found on account database')

email_confirmed.connect(process_domain_on_email_confirmed)
