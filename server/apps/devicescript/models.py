import uuid

from django.conf import settings
from django.db import models
from django.db.models import Max
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.org.models import Org
from apps.s3file.models import S3File
from apps.utils.gid.convert import gid_join, int32gid

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')


def increment_version_slug():
    pass


class DeviceScript(models.Model):
    """
    A physical binary blob that contains instructions for a device to update itself.
    This does not have any targeting instructions, it is just a record indicating the
    raw file itself and a unique id (represented with a gid)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Unique identifier for a given script
    gid = models.PositiveIntegerField(unique=True)

    slug = models.CharField(max_length=20, editable=False)

    name = models.CharField(max_length=50)

    major_version = models.IntegerField(_('Major'), default=0)
    minor_version = models.IntegerField(_('Minor'), default=0)
    patch_version = models.IntegerField(_('Patch'), default=0)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    # Firmware Script
    file = models.OneToOneField(S3File, on_delete=models.CASCADE, blank=True, null=True)

    # Organization that owns (made) the script
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='device_scripts')
    released = models.BooleanField(_('Mark as released (published)'), default=False)
    released_on = models.DateField(_('Released Date'), blank=True, null=True)

    notes = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['org', 'name', 'gid']
        unique_together = (('org', 'name', 'major_version', 'minor_version', 'patch_version'),)

    def __str__(self):
        return '{0} ({1} {2})'.format(self.slug, self.name, self.version)

    @property
    def formatted_gid(self):
        return int32gid(self.gid)

    def save(self, *args, **kwargs):
        if not self.gid:
            stats = DeviceScript.objects.all().aggregate(Max('gid'))
            if stats and 'gid__max' in stats and stats['gid__max']:
                self.gid = stats['gid__max'] + 1
            else:
                self.gid = 1
            self.slug = gid_join(['z', self.formatted_gid])
        super(DeviceScript, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('ota:script:detail', args=(self.org.slug, self.slug,))

    @property
    def version(self):
        return 'v{0}.{1}.{2}'.format(self.major_version, self.minor_version, self.patch_version)
