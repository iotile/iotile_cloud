import uuid
from django.db import models
from django.conf import settings
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.db.models import Manager

from apps.component.models import Component
from apps.org.models import Org, OrgMembership
from apps.s3images.models import S3Image

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')


class DeviceTemplateManager(Manager):
    """
    Manager to help with Device Templates
    """

    def create_template(self, org, created_by, external_sku, active=True, *args, **kwargs):
        template = self.model(
            external_sku=external_sku,
            org=org,
            active=active,
            created_by=created_by
        )
        for key in kwargs:
            assert(hasattr(template, key))
            setattr(template, key, kwargs[key])

        template.save()
        return template

    def active_templates(self):
        return self.filter(active=True)

    def get_from_request(self, request):
        resolver_match = request.resolver_match
        if resolver_match:

            if 'template_id' in resolver_match.kwargs:
                template_id = resolver_match.kwargs['template_id']

                return self.model.objects.get(pk=template_id)

        return None


class DeviceTemplate(models.Model):
    """
    A DeviceTemplate represents an IOTile Product (i.e. a POD)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Vendors can define both an external and internal SKU
    # The external sku is used on customer facing documents, and can change
    # The internal sku should never change once defined for a given product
    external_sku = models.CharField(_('SKU/Name'),  max_length=50)
    internal_sku = models.CharField(max_length=50, default='', blank=True)
    family = models.CharField(max_length=50, default='')

    major_version = models.IntegerField(_('Major'), default=0)
    minor_version = models.IntegerField(_('Minor'), default=0)
    patch_version = models.IntegerField(_('Patch'), default=0)

    released_on = models.DateField(_('Released Date'))
    slug = models.SlugField(max_length=60, unique=True)

    # 20 bit number that indicates the combination of FW running on each tile.
    # This is the ID that is actually stored on an IOTile POD.
    # The version is the version of the OS. A minor change (decimal) represents a backwards compatible change
    os_tag = models.PositiveIntegerField(_('Device OS Tag'), default=0)
    os_major_version = models.PositiveIntegerField(_('Device OS Major Version'), default=0)
    os_minor_version = models.PositiveIntegerField(_('Device OS Major Version'), default=0)

    # 20 bit number that indicates the combination of HW tiles.
    # This represents the actual physical HW differences
    hw_tag = models.PositiveIntegerField(_('Device HW Tag'), default=0)
    hw_major_version = models.PositiveIntegerField(_('Device HW Major Version'), default=0)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_templates')

    # Organization that owns (made) the component
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='templates', null=True, blank=True)
    active = models.BooleanField(default=True)

    components = models.ManyToManyField(Component, blank=True)

    # Product Images
    images = models.ManyToManyField(S3Image, blank=True)

    description = models.TextField(_('Short Description'), blank=True)

    objects = DeviceTemplateManager()

    class Meta:
        ordering = ['external_sku', 'major_version', 'minor_version', 'patch_version']
        unique_together = (('external_sku', 'major_version', 'minor_version', 'patch_version'),)
        verbose_name = _("Device Template")
        verbose_name_plural = _("Device Templates")

    def __str__(self):
        name = '{0} ({1})'.format(self.external_sku, self.version)
        if not self.active:
            name += ' *'
        return name

    def save(self, *args, **kwargs):
        name = '{0}--v{1}-{2}-{3}'.format(self.external_sku,
                                          self.major_version,
                                          self.minor_version,
                                          self.patch_version)
        self.slug = slugify(name)
        super(DeviceTemplate, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('template:detail', args=(self.slug,))

    @property
    def name(self):
        return self.external_sku

    @property
    def version(self):
        return 'v{0}.{1}.{2}'.format(self.major_version, self.minor_version, self.patch_version)

    @property
    def os_version(self):
        return 'v{}.{}'.format(self.os_major_version, self.os_minor_version)

    @property
    def os_tag_and_version(self):
        return '{} {}'.format(self.os_tag, self.os_version)

    @property
    def hw_version(self):
        return 'v{}'.format(self.hw_major_version)

    @property
    def hw_tag_and_version(self):
        return '{} {}'.format(self.hw_tag, self.hw_version)

    def is_owner(self, user):
        if user.is_anonymous:
            return False
        if user.is_staff:
            return True

        if self.org:
            # If not active, only Owner Org can see it
            return self.org.has_write_access(user)

        return False

    def has_access(self, user):
        if user.is_staff:
            return True

        if not self.active and self.org:
            # If not active, only Owner Org can see it
            return self.org.has_access(user)

        return self.active

    def has_write_access(self, user):
        if user.is_staff:
            return True

        if self.org:
            # If not active, only Owner Org can see it
            return self.org.is_admin(user)

        return False

    def get_poster_image(self):
        image = self.images.first()
        if image:
            return image
        return None


class DeviceSlot(models.Model):

    template = models.ForeignKey(DeviceTemplate, on_delete=models.CASCADE, related_name='slots')
    component = models.ForeignKey(Component, on_delete=models.CASCADE, related_name='slots')

    number = models.IntegerField()

    class Meta:
        ordering = ['id']
        unique_together = (('template', 'component', 'number',),)

    def __str__(self):
        return '{0}:{1}'.format(self.template.name, self.component.name)
