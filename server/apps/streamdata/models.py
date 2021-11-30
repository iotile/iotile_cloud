import datetime
import logging

from django_pandas.managers import DataFrameManager

from django.db import models
from django.db.models import Manager
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.datablock.models import DataBlock
from apps.org.models import Org, OrgMembership
from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.streamalias.helpers import StreamAliasHelper
from apps.utils.aws.s3 import get_s3_url
from apps.utils.enums import STATUS_CHOICES, TYPE_CHOICES
from apps.utils.timezone_utils import Y2K, convert_to_utc

logger = logging.getLogger(__name__)


def get_timestamp_from_utc_device_timestamp(device_timestamp):
    """
    For devices with RTC support, use device_timestamp to generate a proper datetime

    :param device_timestamp: device timestamp with MSB set
    :return: datetime in UTC
    """
    assert device_timestamp is not None and bool(int(device_timestamp))
    ts_seconds = int(device_timestamp) & ((1 << 31) - 1)
    delta = datetime.timedelta(seconds=ts_seconds)
    # UTC device timestamp is based on 2000-01-01
    return convert_to_utc(Y2K + delta)


class StreamDataManager(Manager):
    """
    Manager to help with Device Management
    """

    def user_data_qs(self, user, project_slug=None):
        if project_slug:
            try:
                project = Project.objects.get(slug=project_slug)
                if project.has_access(user):
                    return self.model.objects.filter(project_slug=project_slug)
                else:
                    return None
            except Project.DoesNotExist:
                return None
        else:
            membership = OrgMembership.objects.select_related('org').filter(user=user)
            orgs = Org.objects.filter(id__in=[m.org.id for m in membership])
            devices = Device.objects.select_related('org').filter(org__in=[org.id for org in orgs])
            blocks = DataBlock.objects.select_related('org').filter(org__in=[org.id for org in orgs])
            slugs = [device.slug for device in devices] + [block.slug for block in blocks]
            return self.model.objects.filter(device_slug__in=slugs)

    def filter_by_slug(self, value):
        """
        Automatically filter by a universal slug.
        :param value: Slug representing stream, variable, device, data block, or stream alias
        :return: queryset
        """
        queryset = self.model.objects.all()

        if value == 'future':
            # Undocumented feature for Staff to be able to look for anomalies:
            # Data in the future
            return queryset.filter(timestamp__gte=timezone.now())

        elements = value.split('--')
        if elements[0] == 's':
            return queryset.filter(stream_slug=value)
        elif elements[0] == 'v':
            return queryset.filter(variable_slug=value)
        elif elements[0] == 'd':
            return queryset.filter(device_slug=value)
        elif elements[0] == 'b':
            return queryset.filter(device_slug=value)
        elif elements[0] == 'a':
            # ordering by timestamp makes more sense for stream aliases
            return queryset.filter(StreamAliasHelper.get_filter_q_for_slug(value)).order_by('timestamp')
        return self.model.objects.none()


class StreamDataBase(models.Model):
    """
    This is the Abstract Class used for all stream data models
    Because Data Streams is stored on a secondary database (Redshift),
    none of these models can have foreign keys to any of the tables
    on the primary database. This is why all data models use stream,
    project, device and variable slugs for easy filtering.

    All data streams represent a timeseries, where every record has a
    timestamp representing the time when the data was acquired.
    """

    stream_slug = models.CharField(max_length=39, default='', null=True)

    project_slug = models.CharField(max_length=12, default='', null=True)
    device_slug = models.CharField(max_length=33, default='', null=True)
    variable_slug = models.CharField(max_length=18, default='', null=True)

    # Raw timestamp of device in seconds sincce the device reboot
    device_timestamp = models.BigIntegerField(null=True, blank=True)

    # Absolute timestamp computed by the gateway and/or server (in UTC)
    timestamp = models.DateTimeField(null=True, blank=True)

    # Streamers add an incremental ID to each data point.
    # the default=0 means not set
    streamer_local_id = models.PositiveIntegerField(default=0)

    # Some devices do not have the concept of absolute timing,
    # so time is relative to the time it first boots.
    # If the device reboots, the timestamp will get reset to zero
    # but existing records before the reboot will still be included
    # in the streamer reports. These records will have time stamps
    # relative to an unknown base.
    # These data points will get a dirty_ts=True
    dirty_ts = models.BooleanField(default=False)

    status = models.CharField(max_length=3, choices=STATUS_CHOICES, default='unk')

    objects = StreamDataManager()
    df_objects = DataFrameManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # NOTE: bulk_create operations will NOT call save()
        self.deduce_slugs_from_stream_id()

        super(StreamDataBase, self).save(*args, **kwargs)

    def deduce_slugs_from_stream_id(self):
        elements = self.stream_slug.split('--')
        assert len(elements) == 4
        if elements[2].split('-')[0] == '0000':
            self.device_slug = '--'.join(['d', elements[2]])
            self.project_slug = '--'.join(['p', elements[1]])
        else:
            # This is a DataBlock stream
            self.device_slug = '--'.join(['b', elements[2]])
            self.project_slug = ''
        self.variable_slug = '--'.join(['v', elements[1], elements[3]])

    @property
    def incremental_id(self):
        """Preferred name. Will eventually change the model to use it"""
        return self.streamer_local_id

    @property
    def has_utc_synchronized_device_timestamp(self):
        return self.device_timestamp is not None and bool(int(self.device_timestamp) & (1 << 31)) and int(self.device_timestamp) != 0xFFFFFFFF

    def sync_utc_timestamp_from_device(self):
        """
        This function sets the timestamp with a device generated UTC timestamp.
        Newer devices with RTC support can generate a UTC device_timestamp
        In this case, a real datetime can be calculated from it
        """
        assert self.has_utc_synchronized_device_timestamp
        self.timestamp = get_timestamp_from_utc_device_timestamp(self.device_timestamp)


class StreamData(StreamDataBase):
    """
    This is the main data table
    Represents a traditional numberic time series
    """

    type = models.CharField(max_length=3, choices=TYPE_CHOICES, default='Num')

    # New general purpose value for any type of numerical value
    # Assumes the Stream has a VarType definiing the internal
    # units for the given type (e.g. 'Liters' for 'Volume')
    value = models.FloatField(null=True, blank=True)

    # int_value is the old value that represented the raw
    # device value that the device is sending.
    # Depending on the sensor graph, this raw value will be
    # translated to self.value which represents data for a
    # given data type
    int_value = models.BigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['streamer_local_id', 'stream_slug', 'timestamp']
        verbose_name = _("Stream Data Entry")
        verbose_name_plural = _("Stream Data Entries")

    def __str__(self):
        return '{0}:{1} --> {2} - {3}'.format(self.stream_slug, str(self.incremental_id),
                                              self.timestamp, self.value)

    @property
    def raw_value(self):
        """Preferred name. Will eventually change table"""
        return self.int_value
