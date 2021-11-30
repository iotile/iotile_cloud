import datetime
import logging
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Manager
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.org.models import Org, OrgMembership
from apps.physicaldevice.models import Device
from apps.utils.gid.convert import formatted_gtid, int16gid
from apps.utils.iotile.streamer import STREAMER_SELECTOR
from apps.utils.timezone_utils import str_utc

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
logger = logging.getLogger(__name__)


def get_streamer_error_s3_bucket_name():
    return getattr(settings, 'STREAMER_S3_BUCKET_NAME')



class StreamerManager(Manager):
    """
    Manager to help with Streamer records
    """

    def user_streamer_qs(self, user):
        membership = OrgMembership.objects.filter(user=user).select_related('org')
        orgs = Org.objects.filter(id__in=[m.org.id for m in membership])
        devices = Device.objects.filter(org_id__in=orgs, project__isnull=False, active=True)
        return self.model.objects.filter(device__in=devices)


class Streamer(models.Model):

    # Slug format: t--<device_id>--<index>. e.g. 't--0000-0000-0000-0001--0001'
    slug = models.SlugField(max_length=28, unique=True)

    # Devices can have up to six streamers (even we are designing for many more)
    # The index represents the streamer id within the given device
    index = models.IntegerField(default=0)

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='streamers')

    # last_id represents the largest StreamData id count committed to the StreamData database
    # for the given streamer
    last_id = models.BigIntegerField(default=0)

    # Store the last known reboot time
    last_reboot_ts = models.DateTimeField(null=True, blank=True)

    # TODO: Remove once all streamers have been updated with new selector field
    #      Main reason not to do it now is that most test use bad report files with incorrect selectors
    #      so we will need to regenerate all the reports
    is_system = models.BooleanField(default=False)

    selector = models.PositiveIntegerField(default=0)
    process_engine_ver = models.PositiveIntegerField(default=0)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    objects = StreamerManager()

    class Meta:
        ordering = ['device', 'index']
        unique_together = (('device', 'index', ))
        verbose_name = _("Device Streamer")
        verbose_name_plural = _("Device Streamers")

    def save(self, *args, **kwargs):
        self.slug = formatted_gtid(did=self.device.formatted_gid, index=self.formatted_index)
        if self.selector:
            self.is_system = (self.selector == STREAMER_SELECTOR['SYSTEM'])
        super(Streamer, self).save(*args, **kwargs)

    def __str__(self):
        return '{}'.format(self.slug)

    @property
    def formatted_index(self):
        return int16gid(self.index)

    def get_error_s3_bucket(self):
        return get_streamer_error_s3_bucket_name()

    def get_error_s3_key(self):
        key_format = getattr(settings, 'STREAMER_S3_KEY_FORMAT')
        error_relative_key = 'errors/{0}'.format(datetime.datetime.utcnow().isoformat())
        return key_format.format(slug=self.slug, uuid=error_relative_key)

    @property
    def triggers_block_completeness(self):
        return self.is_system

    def update_type_if_needed(self, selector):
        if not self.selector:
            self.selector = selector
            if self.is_system != (selector == STREAMER_SELECTOR['SYSTEM']):
                self.is_system = (selector == STREAMER_SELECTOR['SYSTEM'])
            self.save()


class StreamerReport(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    streamer = models.ForeignKey(Streamer, on_delete=models.CASCADE, related_name='reports')
    original_first_id = models.BigIntegerField(null=True, blank=True)
    original_last_id = models.BigIntegerField(null=True, blank=True)
    actual_first_id = models.BigIntegerField(null=True, blank=True)
    actual_last_id = models.BigIntegerField(null=True, blank=True)
    sent_timestamp = models.DateTimeField(null=True, blank=True)

    # sent_timestamp in report header
    device_sent_timestamp = models.BigIntegerField(null=True, blank=True)

    # rpt_id in report header
    incremental_id = models.BigIntegerField(null=True, blank=True)

    time_epsilon = models.FloatField(default=1, blank=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return 'streamer-report-{0}'.format(self.id)

    def delete(self, using=None, keep_parents=False):

        # Need to send SNS message for a Lambda to go delete S3 files
        logger.warning('TODO: Need to Delete S3 file: {0}'.format(self.get_dropbox_s3_bucket_and_key()))

        super(StreamerReport, self).delete(using, keep_parents)

    @property
    def successful(self):
        result = (self.actual_first_id is not None) and (self.actual_last_id is not None)
        return result

    @property
    def status(self):
        if not self.original_first_id and not self.original_last_id:
            result = "Scheduled"
        else:
            if self.actual_first_id is not None and self.actual_last_id is not None:
                result = "Success"
            else:
                result = "Fail"
        return result

    # This may differ from the actual number of data point added
    @property
    def num_entries(self):
        if self.actual_first_id and self.actual_last_id:
            return self.actual_last_id - self.actual_first_id + 1
        return 0

    def get_dropbox_s3_bucket_and_key(self, ext='.bin'):
        # Key: /<stage>/<streamer>/2017/08/31/08/<uuid>.<ext>
        bucket = getattr(settings, 'STREAMER_REPORT_DROPBOX_BUCKET_NAME')

        # Compute the path: /2017/08/31/08/
        dt_template = getattr(settings, 'STREAMER_REPORT_DROPBOX_KEY_DATETIME_FORMAT_V2')
        ts = self.sent_timestamp or timezone.now()
        path = ts.strftime(dt_template)

        # '{stage}/{{streamer}}/{{path}}/{{uuid}}.{{ext}}'.format(stage=SERVER_TYPE)
        key_template = getattr(settings, 'STREAMER_REPORT_DROPBOX_KEY_FORMAT_V2')
        key = key_template.format(streamer=self.streamer.slug, path=path, uuid=str(self.id), ext=ext)
        return bucket, key

    def get_s3_metadata(self):
        return {
            'x-amz-meta-streamer': self.streamer.slug,
            'x-amz-meta-uuid': str(self.id),
            'x-amz-meta-sent': str_utc(self.sent_timestamp),
            'x-amz-meta-sigid': str(self.incremental_id),
            'x-amz-meta-engine-ver': 'v{}'.format(self.streamer.process_engine_ver),
            'x-amz-meta-user': self.created_by.slug
        }
