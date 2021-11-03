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
from django.db import IntegrityError


from apps.utils.aws.s3 import get_s3_url

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
logger = logging.getLogger(__name__)

class S3FileManager(Manager):
    """
    Manager to help with S3Image
    """

    def create_file(self, uuid, name, key, user, bucket=settings.S3FILE_BUCKET_NAME):
        file = self.model(id=uuid, title=name, bucket=bucket,
                          key=key, created_by=user)
        try:
            file.save()
        except IntegrityError:
            return None

        return file

    def set_or_create_file(self, uuid, name, key, user, bucket=settings.S3FILE_BUCKET_NAME):
        """
        Check if s3file with UUID exists. If it does, update key fields. If it doesn't,
        create one

        :return: New or modified s3file
        """
        file, created = self.get_or_create(
            id=uuid,
            defaults={
                'title': name,
                'bucket': bucket,
                'key': key,
                'created_by': user
            }
        )
        if not created:
            if name != file.title or key != file.key or bucket != file.bucket:
                logger.info('Updating S3File {}'.format(str(file.id)))
                file.title = name
                file.bucket = bucket
                file.key = key
                file.created_by = user
                file.save()

        return file


class S3File(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    title = models.CharField(max_length=100, null=True, blank=True)

    bucket = models.CharField(max_length=50)
    key = models.CharField(max_length=160, unique=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='s3files')

    objects = S3FileManager()

    class Meta:
        ordering = ['bucket', 'key']
        verbose_name = _("S3 File")
        verbose_name_plural = _("S3 Files")

    def __str__(self):
        return self.key

    def save(self, *args, **kwargs):
        super(S3File, self).save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):

        if self.bucket and self.key:
            # Need to send SNS message for a Lambda to go delete S3 files
            logger.warning('TODO: Need to Delete File {0}'.format(self.key))

        super(S3File, self).delete(using, keep_parents)

    def get_absolute_url(self):
        return reverse('s3file:detail', args=(str(self.id),))

    @property
    def url(self):
        #return settings.S3FILE_URL_FORMAT.format(key=self.key)
        return get_s3_url(bucket_name=self.bucket, key_name=self.key)

    @property
    def file_ext(self):
        base, ext = os.path.splitext(self.key)
        return ext

    @property
    def file_type(self):
        ext = self.file_ext
        types = {
            '.jpg': 'image',
            '.jpeg': 'image',
            '.png': 'image',
            '.sgf': 'sgf',
            '.trub': 'device-script',
            '.html': 'html',
            '.sxd': 'SXd',
        }

        if ext in types:
            return types[ext]
        return 'unk'





