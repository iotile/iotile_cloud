import datetime
import logging

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Manager
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from iotile_cloud.utils.gid import IOTileStreamSlug

from apps.devicetemplate.models import DeviceTemplate
from apps.org.models import Org
from apps.project.models import Project
from apps.property.models import GenericProperty
from apps.sensorgraph.models import SensorGraph
from apps.utils.gid.convert import int2did, formatted_gdid
from .state import DEVICE_STATE_CHOICES

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
logger = logging.getLogger(__name__)


class DeviceManager(Manager):
    """
    Manager to help with Device Management
    """

    def get_from_request(self, request):
        resolver_match = request.resolver_match
        if resolver_match:
            if 'device_id' in resolver_match.kwargs:
                device_id = resolver_match.kwargs['device_id']
                device = get_object_or_404(self.model, pk=device_id)
                return device

        return None

    def create_device(self, project, created_by, template, label='', *args, **kwargs):
        if project:
            org = project.org
        else:
            org = None
        device = self.model(
            label=label,
            project=project,
            org=org,
            template=template,
            created_by=created_by
        )
        for key in kwargs:
            assert(hasattr(device, key))
            setattr(device, key, kwargs[key])

        device.save()
        return device

    def user_device_qs(self, user, project=None, all=False):
        orgs = Org.objects.user_orgs_ids(user)
        if not project:
            qs = self.model.objects.select_related('org').filter(org__in=orgs)
        else:
            qs = self.model.objects.select_related('org').filter(org__in=orgs, project=project)

        if not all:
            qs = qs.filter(active=True)

        return qs

    def project_device_qs(self, project=None, all=False):
        qs = self.model.objects.select_related('org').filter(project=project)
        if not all:
            qs = qs.filter(active=True)

        return qs


class Device(models.Model):

    id = models.BigAutoField(primary_key=True)
    slug = models.SlugField(max_length=24, default='')

    org = models.ForeignKey(Org, related_name='devices', null=True, blank=True, on_delete=models.SET_NULL)
    project = models.ForeignKey(Project, related_name='devices', null=True, blank=True, on_delete=models.SET_NULL)
    # All devices need to be built based on a global template, owned by a seller
    template = models.ForeignKey(DeviceTemplate, related_name='devices', null=True, on_delete=models.SET_NULL)

    # Devices are always configured with a Sensor Graph
    sg = models.ForeignKey(SensorGraph, related_name='devices', null=True, blank=True, on_delete=models.SET_NULL)

    # External ID is a general purpose record to represent secondary IDs
    # used mostly for non-iotile devices
    external_id = models.CharField(max_length=24, default='', blank=True)

    # User friendly name
    label = models.CharField(max_length=100, default='', blank=True)

    # GPS Coordinates
    lon = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Id of the last system report being processed
    # updated (only) after processing a system report.
    last_known_id = models.PositiveIntegerField(default=1, blank=True)

    # Last reboot timestamp of the device, which is the timestamp of the last 5c00 data point,
    # updated (only) after processing a system report.
    last_reboot_ts = models.DateTimeField(null=True, blank=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, related_name='created_devices', null=True, blank=True, on_delete=models.SET_NULL)

    claimed_on = models.DateTimeField('claimed_on', null=True, blank=True)
    claimed_by = models.ForeignKey(AUTH_USER_MODEL, related_name='claimed_devices', null=True, blank=True, on_delete=models.SET_NULL)

    active = models.BooleanField(default=True)

    # The state of the device. e.g. Busy when an archive or reset was scheduled
    state = models.CharField(_('Device State'), max_length=2, choices=DEVICE_STATE_CHOICES, default='N1', blank=True)

    objects = DeviceManager()

    class Meta:
        ordering = ['id']
        verbose_name = _("IOTile Device")
        verbose_name_plural = _("IOTile Devices")

    def __str__(self):
        return formatted_gdid(did=self.formatted_gid)

    @property
    def formatted_gid(self):
        if self.id:
            return int2did(self.id)
        return 'UNK'

    @property
    def obj_target_slug(self):
        return self.slug

    @property
    def busy(self):
        return self.state[0] == 'B'

    @property
    def short_slug(self):
        return self.slug.split('-')[-1]

    def set_active_from_state(self):
        self.active = self.state != 'N0'

    def set_state(self, state):
        self.state = state
        self.set_active_from_state()

    def get_properties_qs(self):
        """
        Query for all properties associated with this device slug
        :return: queryset
        """
        return GenericProperty.objects.object_properties_qs(self)

    def get_property_url(self):
        """
        Redirect url for GenericProperty views for this device
        """
        return reverse('org:project:device:property', kwargs={'org_slug': self.org.slug,
                                                              'project_id': self.project.id,
                                                              'pk': self.id})

    def get_absolute_url(self):
        if self.project:
            org = self.project.org
            return reverse('org:project:device:detail', args=(org.slug, str(self.project.id), self.id,))
        return reverse('home')

    def get_edit_url(self):
        if self.project:
            org = self.project.org
            return reverse('org:project:device:edit', args=(org.slug, str(self.project.id), self.id,))
        return reverse('home')

    def get_move_url(self):
        if self.project:
            org = self.project.org
            return reverse('org:project:device:move', args=(org.slug, str(self.project.id), self.id,))
        return reverse('home')

    def get_create_archive_url(self):
        if self.org:
            org = self.org
            return reverse('org:datablock:add', args=(org.slug, self.slug))
        return reverse('home')

    def get_archive_list_url(self):
        return reverse('org:datablock:list', args=(self.org.slug,)) + '?device={}'.format(self.slug)

    def get_reset_url(self):
        return reverse('org:project:device:reset', args=(self.org.slug, str(self.project.id), self.id,))

    def get_trim_url(self):
        return reverse('org:project:device:trim', args=(self.org.slug, str(self.project.id), self.id,))

    def get_mask_url(self):
        return reverse('org:project:device:mask', args=(self.org.slug, str(self.project.id), self.id,))

    def get_trim_by_mask_url(self):
        return reverse('org:project:device:trim-by-mask', args=(self.org.slug, str(self.project.id), self.id,))

    def get_analytics_schedule_url(self):
        return reverse('org:project:device:analytics-schedule', args=(self.org.slug, str(self.project.id), self.id,))

    def get_notes_url(self):
        return reverse('streamnote:list', args=(self.slug,))

    def get_locations_url(self):
        return reverse('devicelocation:map', args=(self.slug,))

    def get_dashboard_url(self):
        if self.project:
            org = self.project.org
            return reverse('org:page:device', args=(org.slug, self.slug,))
        return reverse('home')

    def get_webapp_url(self):
        """
        Get URL for specific device page in WebApp
        e.g.
        https://app-stage.iotile.cloud/#/default/d--0000-0000-0000-00fa
        :return: Absolute URL including domain
        """
        domain = getattr(settings, 'WEBAPP_BASE_URL')
        page_slug = 'default'
        if self.sg:
            if self.sg.ui_extra and 'web' in self.sg.ui_extra:
                extra = self.sg.ui_extra['web']
                if 'pageTemplateSlug' in extra:
                    page_slug = extra['pageTemplateSlug']
        if page_slug == 'oee':
            return '{0}/#/{1}/{2}'.format(domain, page_slug, self.slug)
        return '{0}/#/{1}/device/{2}'.format(domain, page_slug, self.slug)

    def has_access(self, user):
        if user.is_staff:
            return True

        if self.org:
            return self.org.has_access(user)

        if self.project:
            return self.project.has_access(user)

        return self.created_by == user

    def has_write_access(self, user):
        if user.is_staff:
            return True

        if self.org:
            return self.org.has_write_access(user)

        return False

    def get_or_create_status(self):
        return DeviceStatus.get_or_create(self)

    def get_stream_slug_for(self, variable):
        stream_slug = IOTileStreamSlug()
        if self.project:
            stream_slug.from_parts(project=self.project.slug, device=self.slug, variable=variable)
            return stream_slug
        return ''

    def unclaim(self, label):
        self.project = None
        self.org = None
        self.lat = None
        self.lon = None
        self.label = label
        self.claimed_on = None
        self.claimed_by = None
        self.save()

    def get_state_icon(self):
        factory = {
            'N0': '<i class="fa fa-times-circle text-danger"></i>',
            'N1': '<i class="fa fa-check-circle text-success"></i>',
            'B0': '<i class="fa fa-exclamation-circle text-warning"></i>',
            'B1': '<i class="fa fa-exclamation-circle text-warning"></i>',
        }

        return mark_safe(factory[self.state])


@receiver(post_save, sender=Device)
def post_save_device_callback(sender, **kwargs):
    device = kwargs['instance']
    created = kwargs['created']
    if created:
        # CRITICAL. Make sure you do not create an infinite loop with the save()
        device.slug = formatted_gdid(did=device.formatted_gid)
        device.save()


class DeviceStatus(models.Model):

    ALERT_CHOICES = (
        ('UNK', 'Device is in UNK state. No uploads found'),
        ('FAIL', 'Device is in FAIL state'),
        ('OK', 'Device is in OK State'),
        ('DSBL', 'Device status check is disabled'),
    )

    device = models.OneToOneField('Device', on_delete=models.CASCADE, related_name='status')

    # Id of the last system report being processed
    # updated (only) after processing a system report.
    last_known_id = models.BigIntegerField(default=1, blank=True)

    # TS of last report processed
    last_report_ts = models.DateTimeField(null=True, blank=True)

    # Hearthbeat Notifications
    health_check_enabled = models.BooleanField(default=False)
    health_check_period = models.PositiveIntegerField(default=7200)
    last_known_state = models.CharField(max_length=4, choices=ALERT_CHOICES, default='UNK')
    notification_recipients = ArrayField(models.CharField(max_length=64), blank=True, default = list)

    class Meta:
        ordering = ['device', ]
        verbose_name = _("IOTile Device Status")
        verbose_name_plural = _("IOTile Device Statuses")

    def __str__(self):
        return 'Status:{0}'.format(self.device.slug)

    @property
    def alert(self):
        if not self.health_check_enabled:
            return 'DSBL'

        if not self.last_report_ts:
            return 'UNK'

        now = timezone.now()
        if (now - self.last_report_ts) > datetime.timedelta(seconds=self.health_check_period):
            return 'FAIL'
        return 'OK'

    @property
    def alert_verbose(self):
        return dict(DeviceStatus.ALERT_CHOICES)[self.alert]

    @property
    def health_check_period_display(self):
        m, s = divmod(self.health_check_period, 60)
        h, m = divmod(m, 60)
        terms = []
        if h:
            terms.append('{0} hour{1}'.format(h, 's' if h > 1 else ''))
        if m:
            terms.append('{0} minute{1}'.format(m, 's' if m > 1 else ''))
        if s:
            terms.append('{0} second{1}'.format(s, 's' if s > 1 else ''))
        return 'Every ' + ', '.join(terms)

    def update_health(self, ts):
        self.last_report_ts = ts
        self.save()

    def get_absolute_url(self):
        project = self.device.project
        org = self.device.org
        return reverse('org:project:device:health-status', args=(org.slug, str(project.id), self.device.id,))

    @classmethod
    def get_or_create(cls, device):
        """
        Create an object if one does not exist. Return one if it exist
        """
        assert device
        obj, created = DeviceStatus.objects.get_or_create(
            device = device
        )

        return obj
