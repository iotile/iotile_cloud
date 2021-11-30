import json
import logging
import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from iotile_cloud.utils.gid import *

from apps.streamdata.models import StreamDataBase, StreamDataManager
from apps.utils.aws.s3 import get_s3_url
from apps.utils.aws.sns import sns_lambda_message
from apps.utils.enums import EXT_CHOICES

SNS_DELETE_S3 = getattr(settings, 'SNS_DELETE_S3')

logger = logging.getLogger(__name__)


class StreamEventData(StreamDataBase):
    # We need a UUID to use on the s3 key. Cannot just use the record
    # id as the id is not known until after the record is committed to
    # the database, which is a problem with kinesis firehose
    uuid = models.UUIDField(max_length=38, default=uuid.uuid4, editable=False)
    s3_key_path = models.CharField(max_length=20, default='', null=True, blank=True)

    ext = models.CharField(max_length=10, choices=EXT_CHOICES, default='json', null=True, blank=True)

    # We want to have a json string with a key-value store to allow us to
    # store processed summary information related to the event data.
    # Redshift does not support the Postgress Json field, so we need to do
    # this manually
    extra_data = models.JSONField(null=True, blank=True)

    # The format version determines how the bucket/key is computer
    #   - V1: Uses STREAM_EVENT_DATA_BUCKET_NAME and STREAM_EVENT_DATA_S3_KEY_FORMAT
    #   - V2: Uses its own self.s3_key_path instead of STREAM_EVENT_DATA_S3_KEY_FORMAT
    format_version = models.IntegerField(default=2)

    class Meta:
        ordering = ['stream_slug', 'streamer_local_id', 'timestamp']
        verbose_name = _("Stream Event Entry")
        verbose_name_plural = _("Stream Event Entries")

    def __str__(self):
        return '{0}:{1} --> {2} - {3}'.format(self.stream_slug,  str(self.incremental_id),
                                              self.timestamp, self.s3key)

    def set_s3_key_path(self):
        dt_template = getattr(settings, 'STREAM_EVENT_DATA_S3_KEY_DATETIME_FORMAT_V2')
        now = timezone.now()
        self.s3_key_path = now.strftime(dt_template)

    @property
    def s3bucket(self):
        # For v1, s3 Bucket is hard-coded to a single location based on
        # STREAM_EVENT_DATA_BUCKET_NAME.
        # If we ever need to use different locations, this property
        # should become a real table column in the database
        if self.format_version <= 2:
            return getattr(settings, 'STREAM_EVENT_DATA_BUCKET_NAME')
        return None

    @property
    def s3key(self):
        if self.format_version == 2 and self.s3_key_path != '':
            # For v2, s3 path is stored on the record itself and constructed
            # as /<type>/2017/08/31/08/<uuid>.<ext>
            key_template = getattr(settings, 'STREAM_EVENT_DATA_S3_KEY_FORMAT_V2')
            return key_template.format(path=self.s3_key_path, id=str(self.uuid), ext=self.ext)
        elif self.format_version == 1 and self.stream_slug:
            # For v1, s3 Key is hard-coded to a predefined format based on
            # STREAM_EVENT_DATA_S3_KEY_FORMAT.
            key_template = getattr(settings, 'STREAM_EVENT_DATA_S3_KEY_FORMAT_V1')

            # HACK BEGIN For blocks, need to use the original stream ID
            stream_slug = IOTileStreamSlug(self.stream_slug)
            parts = stream_slug.get_parts()
            block_slug = IOTileBlockSlug(parts['device'])
            device_slug = IOTileDeviceSlug(block_slug.get_id())
            project_slug = IOTileProjectSlug(parts['project'])
            variable_slug = IOTileVariableSlug(parts['variable'])
            stream_slug.from_parts(project_slug, device_slug, variable_slug)
            # HACK END

            return key_template.format(slug=str(stream_slug), id=str(self.uuid), ext=self.ext)
        return None

    @property
    def url(self):
        if self.s3bucket and self.s3key:
            return get_s3_url(bucket_name=self.s3bucket, key_name=self.s3key)
        return None

    @property
    def summary(self):
        if self.extra_data:
            return self.extra_data
        return None

    @property
    def has_raw_data(self):
        return (self.s3key != None and self.s3key != '')

    def set_summary_value(self, name, value):
        if not self.extra_data:
            self.extra_data = {}
        self.extra_data[name] = value

    def get_summary_value(self, name):
        if self.extra_data:
            if name in self.extra_data:
                return self.extra_data[name]

        return None


@receiver(pre_delete, sender=StreamEventData)
def pre_delete_streamevent_callback(sender, **kwargs):
    event = kwargs['instance']
    logger.info('pre-delete stream event {0} of stream'.format(str(event.uuid), event.stream_slug))
    msg = [{
        "uuid": str(event.uuid),
        "bucket": event.s3bucket,
        "key": event.s3key
    }]
    sns_lambda_message(SNS_DELETE_S3, msg)
