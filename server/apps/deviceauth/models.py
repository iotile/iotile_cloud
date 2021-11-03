import logging
import random
import string

from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.dispatch import receiver
from django.db.models import Manager

from apps.physicaldevice.models import Device

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
logger = logging.getLogger(__name__)


def _gen_secret_key():
    return ''.join([random.SystemRandom().choice(string.ascii_letters + string.digits + string.punctuation) for _ in
                    range(50)])


class DeviceKeyManager(Manager):
    """
    Manager to help with Device Management
    """


    def get_or_create_ajwt_device_key(self, device, created_by=None):
        if created_by is None:
            created_by = device.claimed_by
        try:
            key = DeviceKey.objects.get(slug=device.slug, type='A-JWT-KEY')
        except DeviceKey.DoesNotExist:
            key = DeviceKey.objects.create(
                slug=device.slug,
                downloadable=False,
                secret=_gen_secret_key(),
                type='A-JWT-KEY',
                created_by=created_by
            )

        return key

    def create_device(self, slug, type, secret, downloadable, created_by):
        key = self.model(
            type=type,
            slug=slug,
            downloadable=downloadable,
            secret=secret,
            created_by=created_by
        )
        key.save()
        return key

    def get_for_download(self, slug, type):
        return DeviceKey.objects.get(slug=slug, downloadable=True, type=type)


class DeviceKey(models.Model):

    slug = models.SlugField(max_length=24)

    TYPE_CHOICES = (
        ('USR', 'User Key'),
        ('SSH', 'SSH Key'),
        ('X-API-KEY', 'API Gateway Key'),
        ('A-JWT-KEY', 'Secret Key for a-jwt generation'),
        ('MQTT', 'MQTT Password for device topics'),
    )

    type = models.CharField(max_length=16, choices=TYPE_CHOICES, default='USR')
    secret = models.TextField()

    # The user should not be able to download most keys
    downloadable = models.BooleanField(default=False, blank=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    objects = DeviceKeyManager()

    class Meta:
        ordering = ['slug', 'type',]
        unique_together = (('slug', 'type',),)
        verbose_name = _("Device Key")
        verbose_name_plural = _("Device Keys")

    def __str__(self):
        return '{0}:{1}'.format(self.type, self.slug)
