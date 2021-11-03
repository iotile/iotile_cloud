from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError

from apps.utils.gid.convert import int2did
from apps.physicaldevice.models import Device
from apps.org.models import Org, OrgMembership
from apps.utils.gid.convert import formatted_fleet_id, int2fleet_id

from apps.sensorgraph.models import SensorGraph

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')


class FleetManager(models.Manager):
    """
    Manager to help with Device Management
    """

    def user_fleets_qs(self, user):
        membership = OrgMembership.objects.filter(user__id=user.id).select_related('org')
        orgs = Org.objects.filter(id__in=[m.org_id for m in membership])

        return self.model.objects.filter(org__in=orgs).select_related('org', 'created_by')


class Fleet(models.Model):
    """
    A Fleet represents a group of devices.
    This group is used to represent networks or configuration profiles.
    Operating on a Fleet is like operating on ALL devices in the given fleet.
    """

    slug = models.SlugField(max_length=17)

    name = models.CharField(max_length=50)
    description = models.TextField(blank=True, default='')
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='fleets')

    # Is the fleet representing a network with gateways acting as bridges
    is_network = models.BooleanField(default=False)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    members = models.ManyToManyField(Device, through='FleetMembership')

    objects = FleetManager()

    class Meta:
        ordering = ['org', 'name']
        unique_together = (('org', 'name',) )
        verbose_name = _("Fleet")
        verbose_name_plural = _("Fleets")

    def __str__(self):
        return '{0} - {1}'.format(self.slug, self.name)

    @property
    def formatted_gid(self):
        if self.id:
            return int2fleet_id(self.id)
        return 'UNK'

    @property
    def obj_target_slug(self):
        return self.slug

    def get_absolute_url(self):
        return reverse('org:fleet:detail', args=(str(self.org.slug), self.slug,))

    def has_access(self, user):
        if user.is_staff:
            return True

        if self.org:
            return self.org.has_access(user)

        return self.created_by == user

    def has_write_access(self, user):
        if user.is_staff:
            return True

        if self.org:
            return self.org.has_permission(user, 'can_manage_ota')

        return False

    def register_device(self, device, is_access_point=False, always_on=False):
        membership = FleetMembership(device=device, fleet=self, is_access_point=is_access_point, always_on=always_on)
        if membership.clean():
            membership.save()
        else:
            print('Not clean: {0}, {1}'.format(device.org, self.org))

    def is_member(self, device):
        return device.fleet_set.filter(id=self.id).exists()


class FleetMembership(models.Model):
    """
    Represents the pairing of a device and a fleet.
    """
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    fleet = models.ForeignKey(Fleet, on_delete=models.CASCADE, blank=True, null=True)

    # True if device should always be up
    always_on = models.BooleanField(default=False)
    # True if device has internet and can act as gateway
    # (meaning it reads other devices).
    is_access_point = models.BooleanField(default=False)

    created_on = models.DateTimeField('created_on', auto_now_add=True)

    class Meta:
        ordering = ['fleet', 'device']
        unique_together = (('device', 'fleet',) )
        verbose_name = _("Fleet Membership")
        verbose_name_plural = _("Fleet Memberships")

    def __str__(self):
        return '{0}::{1}'.format(self.device.slug, self.fleet.slug)

    def get_edit_url(self):
        return reverse('org:fleet:member-edit', args=(str(self.fleet.org.slug), self.fleet.slug, self.id))

    def get_delete_url(self):
        return reverse('org:fleet:member-delete', args=(str(self.fleet.org.slug), self.fleet.slug, self.id))

    def clean(self):
        if self.fleet and self.device.org != self.fleet.org:
            raise ValidationError(_('Device and Fleet must be part of same Org'))
        return True

    def type_icons(self):
        icons = ''
        if self.always_on:
            icons += '<i class="fa fa-power-off" aria-hidden="true" title="Always On"></i>'
        if self.is_access_point:
            icons += '<i class="fa fa-wifi" aria-hidden="true" title="Access Point"></i>'
        return icons


@receiver(post_save, sender=Fleet)
def post_save_fleet_callback(sender, **kwargs):
    fleet = kwargs['instance']
    created = kwargs['created']
    if created:
        # CRITICAL. Make sure you do not create an infinite loop with the save()
        fleet.slug = formatted_fleet_id(fleet.formatted_gid)
        fleet.save()