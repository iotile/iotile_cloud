import uuid

from django.conf import settings
from django.db import models
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.org.models import Org
from apps.s3images.models import S3Image

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')


class Component(models.Model):

    COMPONENT_CHOICES = (
        ('BTC', 'Controller'),
        ('SEN', 'Sensor'),
        ('COM', 'Communication'),
        ('IOT', 'Other IOTile'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Vendors can define both an external and internal SKU
    # The external sku is used on customer facing documents, and can change
    # The internal sku should never change once defined for a given product
    external_sku = models.CharField(_('SKU/Name'),  max_length=50)
    internal_sku = models.CharField(max_length=50, default='', blank=True)

    slug = models.SlugField(max_length=60, unique=True)

    type = models.CharField(max_length=3, choices=COMPONENT_CHOICES)

    major_version = models.IntegerField(_('Major'), default=0)
    minor_version = models.IntegerField(_('Minor'), default=0)
    patch_version = models.IntegerField(_('Patch'), default=0)

    # Product Images
    images = models.ManyToManyField(S3Image, blank=True)

    # Organization that owns (made) the component
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='components', null=True, blank=True)
    active = models.BooleanField(default=True)

    # HW tag is a globally unique ID for every different tile
    hw_tag = models.CharField(max_length=20, default='', blank=True)
    # HW name is the string that the 'tile_name IOTile coretools command returns. e.g.
    #    iotile hw --port=bled112 connect 0x24d get 11 tile_name
    hw_name = models.CharField(max_length=20, default='', blank=True)

    description = models.TextField(_('Short Description'), blank=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_components')

    class Meta:
        ordering = ['external_sku', 'major_version', 'minor_version', 'patch_version',]
        unique_together = (('external_sku', 'major_version', 'minor_version', 'patch_version', ),)
        verbose_name = _("Component")
        verbose_name_plural = _("Components")

    def __str__(self):
        return '{0} ({1})'.format(self.external_sku, self.version)

    def save(self, *args, **kwargs):
        name = '{0}-{1}-{2}-{3}'.format(self.external_sku,
                                        self.major_version,
                                        self.minor_version,
                                        self.patch_version)

        self.slug = slugify(name)
        super(Component, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('component:detail', args=(str(self.id),))

    @property
    def name(self):
        return self.external_sku

    @property
    def version(self):
        return 'v{0}.{1}.{2}'.format(self.major_version, self.minor_version, self.patch_version)

    def is_owner(self, user):
        if user.is_staff:
            return True

        if self.org:
            # If not active, only Owner Org can see it
            return self.org.has_access(user)

        return False

    def has_access(self, user):
        if user.is_staff:
            return True

        if not self.active and self.org:
            # If not active, only Owner Org can see it
            return self.org.has_access(user)

        return self.active




