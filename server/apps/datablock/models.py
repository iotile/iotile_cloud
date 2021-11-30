from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from iotile_cloud.utils.gid import IOTileProjectSlug, IOTileStreamSlug

from apps.org.models import Org
from apps.physicaldevice.models import Device
from apps.sensorgraph.models import SensorGraph
from apps.utils.gid.convert import formatted_dbid, int2bid, int2did, int2did_short

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')


def get_block_id(device):
    last_block = device.data_blocks.last()
    if last_block:
        new_block_id = last_block.block + 1
    else:
        new_block_id = 1
    return new_block_id


class DataBlock(models.Model):
    """
    A DataBlock represents a block or period of data for a
    given device.
    This is model represents the header for this block of data.
    The header is equivalent to the Device, and in fact has a
    similar global ID: d--<blockId>-<devcieId> where
    blockId is a four digit HEX number, while deviceId is three
    sets of four-digit HEX numbers. so `d--0001-0002-0003-0004
    represents data block 0001 in device 0002-0003-0004.

    This scheme can be used to:
    - Archive Device Data
    - Represent small portions of time, like trips
    """
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='data_blocks', null=True, blank=True)

    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    slug = models.SlugField(max_length=24)

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='data_blocks')
    block = models.PositiveIntegerField()
    sg = models.ForeignKey(SensorGraph, related_name='data_blocks', null=True, blank=True, on_delete=models.SET_NULL)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    completed_on = models.DateTimeField('completed_on', null=True, blank=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['device', 'block']
        unique_together = (('device', 'block',) )
        verbose_name = _("Data block")
        verbose_name_plural = _("Data blocks")

    def save(self, *args, **kwargs):
        '''
        The block ID should always get its slug based on the device slug
        '''
        if self.device:
            # Handle any updates after initial post_save
            self.slug = formatted_dbid(bid=int2bid(self.block),
                                       did=self.device.formatted_gid)
        super(DataBlock, self).save(*args, **kwargs)

    def __str__(self):
        return self.slug

    @property
    def formatted_gid(self):
        if self.device:
            return '-'.join([int2bid(self.block), int2did_short(self.device.id)])
        return 'UNK'

    @property
    def original_device_slug(self):
        # Just replace 'b--' with 'd--'
        slug = self.slug
        slug[0].replace('b', 'd')
        return slug

    @property
    def status(self):
        if self.completed_on:
            return 'Completed on {}'.format(self.completed_on)
        return 'Processing...'

    @property
    def obj_target_slug(self):
        return self.slug

    @property
    def busy(self):
        return False

    def get_absolute_url(self):
        return reverse('org:datablock:detail', args=(self.org.slug, self.slug,))

    def get_edit_url(self):
        return reverse('org:datablock:edit', args=(self.org.slug, self.slug,))

    def get_delete_url(self):
        return reverse('org:datablock:delete', args=(self.org.slug, self.slug,))

    def get_analytics_schedule_url(self):
        return reverse('org:datablock:analytics-schedule', args=(self.org.slug, self.slug,))

    def get_locations_url(self):
        return reverse('devicelocation:map', args=(self.slug,))

    def get_mask_url(self):
        return reverse('org:datablock:mask', args=(self.org.slug, self.slug,))

    def get_webapp_url(self):
        """
        Get URL for specific device page in WebApp
        e.g.
        https://app-stage.iotile.cloud/#/default/b--0001-0000-0000-00fa
        :return: Absolute URL including domain
        """
        domain = getattr(settings, 'WEBAPP_BASE_URL')
        page_slug = 'default'
        if self.device and self.device.sg:
            sg = self.device.sg
            if sg.ui_extra and 'web' in sg.ui_extra:
                extra = sg.ui_extra['web']
                if 'pageTemplateSlug' in extra:
                    page_slug = extra['pageTemplateSlug']
        return '{0}/#/{1}/device/{2}'.format(domain, page_slug, self.slug)

    def has_access(self, user):
        if user.is_staff:
            return True

        if self.org:
            return self.org.has_access(user)

        return self.created_by == user

    def has_write_access(self, user):
        if user.is_staff:
            return True

        if self.org:
            return self.org.has_write_access(user)

        return False

    def get_stream_slug_for(self, variable):
        """
        WARNING: This will return a stream with project set to 0000-0000
                 which may not work if used to fetch archived data/events
                 (which have a project ID)
        :param variable: String representing hex variable
        :return: Stream slug string
        """
        stream_slug = IOTileStreamSlug()
        no_proj_slug = IOTileProjectSlug(0)
        stream_slug.from_parts(project=no_proj_slug, device=self.formatted_gid, variable=variable)

        return str(stream_slug)


