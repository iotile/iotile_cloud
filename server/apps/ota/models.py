from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Manager, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.devicescript.models import DeviceScript
from apps.fleet.models import Fleet
from apps.org.models import Org
from apps.physicaldevice.models import Device

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')


class DeploymentRequestManager(Manager):
    """
    Manager to help with DeploymentRequest management
    """

    def device_deployments_qs(self, device, released=True):
        org = device.org
        fleets = device.fleet_set.all()
        vendors = Org.objects.filter(is_vendor=True)

        # Search for
        # 1. All Deployments that match fleet the device is part of
        # 2. All Deployments that match org that device is owned by
        # 3. All global vendor deployments
        q = Q(fleet__in=fleets) | \
            Q(fleet__isnull=True, org=org) | \
            Q(fleet__isnull=True, org__in=vendors)
        qs = self.model.objects.filter(q)
        if released:
            qs = qs.filter(
                released_on__lte=timezone.now(), completed_on__isnull=True
            )

        return qs

    def released_and_active_qs(self):
        """
        Filter for all released but not completed deployments
        :return:
        """
        return self.model.objects.filter(completed_on__isnull=True, released_on__lte=timezone.now())


class DeviceVersionAttributeManager(Manager):
    """
    Manager to help with DeviceVersionAttribute management
    """

    def current_device_version_qs(self, device):
        # Get the last record of each version type
        # Note that only Postgress allows for specifying the field to use for the distict operation
        qs = DeviceVersionAttribute.objects.filter(device=device).order_by('type', '-updated_ts').distinct('type')
        return qs

    def last_device_version(self, device, type):
        """
        Get last version attribute for a given device and type
        :param device: Device object
        :param type: 'os' or 'sg'
        :return: DeviceVersionAttribute object or None if not found
        """
        version_qs = DeviceVersionAttribute.objects.filter(
            device=device, type=type
        ).order_by('updated_ts')
        return version_qs.last()

class DeviceVersionAttribute(models.Model):
    """
    A record will be automatically created based on a system stream representing a
    device update.
    The current version (for a given type) is the last record.
    """

    TYPE_CHOICES = (
        ('os', 'OS Version'),  # The OS is meant to encompass the physical device
        ('app', 'App Version'), # The App is the sensor graph that is running on top
    )

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='versions')

    type = models.CharField(max_length=3, choices=TYPE_CHOICES)

    # Version information:
    major_version = models.PositiveIntegerField(_('Major'), default=0)
    minor_version = models.PositiveIntegerField(_('Minor'), default=0)

    # 20 bit number that indicates the combination of tiles that the device is running.
    tag = models.PositiveIntegerField()

    # Device's local streamer ID for the StreamData with the updated version
    streamer_local_id = models.BigIntegerField(default=1, blank=True)

    # TS of version update
    updated_ts = models.DateTimeField(null=True, blank=True)

    created_on = models.DateTimeField(auto_now_add=True)

    objects = DeviceVersionAttributeManager()

    class Meta:
        ordering = ['device', 'type', 'major_version', 'minor_version']
        unique_together = (('device', 'type', 'tag', 'major_version', 'minor_version', 'streamer_local_id',),)

    def __str__(self):
        return 'Version({0}) = {1}:{2}:{3}'.format(self.device_id, self.type, self.tag, self.version)

    @property
    def version(self):
        return 'v{0}.{1}'.format(self.major_version, self.minor_version)

    @property
    def version_number(self):
        return float('{0}.{1}'.format(self.major_version, self.minor_version))

    def has_access(self, user):
        if user.is_staff:
            return True

        if self.device:
            return self.device.has_access(user)

        return False


class DeploymentRequest(models.Model):
    """
    A record that targets a DeviceScript to one or more iotile devices.
    This is done using a series of ‘target_selection’ criteria that must be met
    for the script to apply.
    If the script needs to be tweaked for each device, this record also contains
    instructions for how to tweak the raw DeviceScript.
    It has a status key for ‘released’ that controls if agents should actually try to use it.
    """

    script = models.ForeignKey(DeviceScript, on_delete=models.CASCADE,
                               related_name='deployments')

    # If fleet is not set, it represents ALL devices (but such functionality should
    # be restricted to STAFF)
    fleet = models.ForeignKey(Fleet, on_delete=models.SET_NULL, related_name='deployments',
                              blank=True, null=True)

    # TODO, Maybe store as strings formatted as “type:op:value” (e.g. “os_version:gte:1.1”).
    #       Assuming we are ANDing all terms
    selection_criteria = ArrayField(models.CharField(max_length=64), blank=True, default=list)

    # TODO: Not clear if we really need this, given that we will encode into system streams.
    #       Need to think how to represent if we do need it
    side_effect = models.JSONField(blank=True, null=True)

    # Organization that executed the Deployment
    # Usually 'Arch Systems'
    org = models.ForeignKey(Org, on_delete=models.SET_NULL, null=True,
                            related_name='deployment_requests')

    # This record can be created before it is published.
    # The deployment begins when a release date is created (and it is in the past)
    released_on = models.DateTimeField(_('Released Date'), blank=True, null=True)
    # Deployment Request is completed when successful DeploymentActions are created
    # for every Device in the Fleet
    completed_on = models.DateTimeField(_('Completed Date'), blank=True, null=True)

    created_on = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    objects = DeploymentRequestManager()

    class Meta:
        ordering = ['completed_on', 'released_on', 'id']

    def __str__(self):
        return 'DeploymentReq-{0}'.format(self.id)

    def get_absolute_url(self):
        return reverse('ota:request-detail', args=(self.org.slug, self.id))

    @property
    def completed(self):
        return self.completed_on and self.completed_on <= timezone.now()

    def has_access(self, user):
        if user.is_staff:
            return True

        if self.fleet:
            return self.fleet.has_access(user)

        if self.org:
            # All users have access to a Deployment from a vendor or their own Org
            return self.org.is_vendor or self.org.has_access(user)

        return self.created_by == user

    def has_write_access(self, user):
        if user.is_staff:
            return True

        if self.fleet:
            return self.fleet.org.has_permission(user, 'can_manage_ota')

        if self.org:
            return self.org.has_permission(user, 'can_manage_ota')

        return self.created_by == user


class DeploymentAction(models.Model):
    """
    UpdateAttempt: A record posted from a phone or gateway indicating that that device
    attempted to update an iotile device with a DeviceScript based on a DeploymentRequest.
    This is not definitive, that confirmation will come from a value posted by the
    device’s sensor graph.
    """

    deployment = models.ForeignKey(DeploymentRequest, on_delete=models.CASCADE,
                                   related_name='actions')

    device = models.ForeignKey(Device, on_delete=models.CASCADE,
                               related_name='deployment_actions')

    last_attempt_on = models.DateTimeField(_('Last attempted'), blank=True, null=True)

    # True if the gateway or mobile has successfully push an update
    attempt_successful = models.BooleanField(default=False)

    # True if the device has sent confirmation via its streamer report
    device_confirmation = models.BooleanField(default=False)

    # And unstructured data sent by the gateway or mobile
    log = models.TextField(blank=True, null=True)

    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['deployment', 'device', 'created_on',]

    def __str__(self):
        return 'DeploymentAction-{0}'.format(self.id)

    def has_access(self, user):
        if user.is_staff:
            return True

        assert self.deployment
        return self.deployment.has_access(user)
