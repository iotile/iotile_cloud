from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.utils.objects.utils import get_object_by_slug

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')


def get_location_target_by_slug(target_slug):
    target = None
    elements = target_slug.split('--')
    if len(elements) > 1 and elements[0] in ['d', 'b']:
        name, target = get_object_by_slug(target_slug)

    return target


class DeviceLocationManager(models.Manager):
    """
    Manager to help with Device Location Management
    """

    def location_qs(self, user, target_slug):
        target = get_location_target_by_slug(target_slug)

        if target and target.has_access(user):
            return self.model.objects.filter(target_slug=target_slug)
        else:
            return None


class DeviceLocation(models.Model):

    target_slug = models.CharField(max_length=39, default='')

    # Absolute timestamp computed by the gateway and/or server (in UTC)
    timestamp = models.DateTimeField()

    lon = models.DecimalField(_('Longitude'), max_digits=9, decimal_places=6, default=0.0)
    lat = models.DecimalField(_('Latitude'), max_digits=9, decimal_places=6, default=0.0)

    user = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    objects = DeviceLocationManager()

    class Meta:
        ordering = ['target_slug', 'timestamp']
        verbose_name = _("Device Location")
        verbose_name_plural = _("Device Locations")

    def __str__(self):
        return 'LOC({0})={1},{2}'.format(self.target_slug, self.lat, self.lon)

    @property
    def target(self):
        return get_location_target_by_slug(self.target_slug)



