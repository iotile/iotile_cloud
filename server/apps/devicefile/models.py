from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.org.models import Org
from apps.s3file.models import S3File

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')


class DeviceFile(models.Model):
    TYPE_CHOICES = (
        ('os', 'OS Image'),
        ('app', 'App Script'),
    )

    slug = models.SlugField(max_length=60, unique=True)

    type = models.CharField(max_length=5, choices=TYPE_CHOICES)
    tag = models.PositiveIntegerField(_('Tag'),  default=0)

    major_version = models.IntegerField(_('Major'), default=0)
    minor_version = models.IntegerField(_('Minor'), default=0)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    released_by = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='device_files')
    released = models.BooleanField(_('Mark as released (published)'), default=False)

    # Image File (.ship file)
    file = models.OneToOneField(S3File, on_delete=models.CASCADE, blank=True, null=True)

    notes = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['id']
        unique_together = (('type', 'tag', 'major_version', 'minor_version',),)

    def __str__(self):
        return '{0}{1}:v{2}'.format(self.type, self.tag, self.version)

    def save(self, *args, **kwargs):
        self.slug = '{0}{1}--{2}-{3}'.format(self.type, self.tag, self.major_version, self.minor_version)
        super(DeviceFile, self).save(*args, **kwargs)

    @property
    def version(self):
        return '{0}.{1}'.format(self.major_version, self.minor_version)

    def get_absolute_url(self):
        return reverse('ota:file:detail', args=(self.slug,))




