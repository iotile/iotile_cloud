import uuid
import os
import logging
from django.db import models
from django.conf import settings
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.db.models import Manager
from django.utils.safestring import mark_safe

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
logger = logging.getLogger(__name__)


class S3ImageManager(Manager):
    """
    Manager to help with S3Image
    """

    def create_image(self, uuid, title, key, request):
        filename, ext = os.path.splitext(key)
        key_path = os.path.dirname(filename)
        image = self.model(id=uuid, title=title, bucket=settings.S3IMAGE_BUCKET_NAME,
                           key=key_path, ext=ext, created_by=request.user)
        image.save()

        return image


class S3Image(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    title = models.CharField(max_length=60, default='', blank=True)

    bucket = models.CharField(max_length=50)
    key = models.CharField(max_length=1600, unique=True)
    ext = models.CharField(max_length=10, unique=False)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_images')

    objects = S3ImageManager()

    class Meta:
        ordering = ['bucket', 'key']
        verbose_name = _("S3 Image")
        verbose_name_plural = _("S3 Images")

    def __str__(self):
        return self.key

    def save(self, *args, **kwargs):
        super(S3Image, self).save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):

        if self.bucket and self.key:
            # Need to send SNS message for a Lambda to go delete S3 files
            logger.warning('TODO: Need to Delete Images {0}/*.* '.format(self.key))

        super(S3Image, self).delete(using, keep_parents)

    def get_absolute_url(self):
        return reverse('s3image:detail', args=(str(self.id),))

    def get_template_image_url(self, type):
        return settings.S3IMAGE_KEY_FORMAT.format(uuid=str(self.id), type=type)

    @property
    def original_url(self):
        return '{0}/{1}/{2}{3}'.format(settings.S3IMAGE_CDN, self.key, 'original', self.ext)

    @property
    def medium_url(self):
        # See serverless/s3image Lambda function to see image size specs
        return self.get_template_image_url('medium')

    @property
    def thumbnail_url(self):
        # See serverless/s3image Lambda function to see image size specs
        return self.get_template_image_url('thumbnail')

    @property
    def tiny_url(self):
        # See serverless/s3image Lambda function to see image size specs
        return self.get_template_image_url('tiny')

    def thumbnail_image_tag(self):
        return mark_safe('<img src="{0}" width="100" height="100" />'.format(self.thumbnail_url))


