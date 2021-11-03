import logging
import uuid

from django.db import connections, models

from apps.utils.data_helpers.misc import update_every_slug
from apps.utils.enums import EXT_CHOICES, STATUS_CHOICES, TYPE_CHOICES

logger = logging.getLogger(__name__)


def get_default_uuid():
    """Generate a random string in UUID format"""
    return str(uuid.uuid4())


class StreamTimeSeries(models.Model):
    """
    This is the Abstract Class used for all stream time series models
    Because Stream Time Series are stored on their own database,
    none of these models can have foreign keys to any of the tables
    on the main database. This is why all data models use stream,
    project, device, block, and variable IDs for easy filtering.

    Every record has a timestamp representing the time when the data
    was acquired.
    """

    stream_slug = models.CharField(max_length=39, default='', null=True)

    # Additional fields that derive from the stream slug but are
    # added to facilitate querying. They are stored using integers.
    project_id = models.BigIntegerField(null=True, blank=True)
    device_id = models.BigIntegerField(null=True, blank=True)
    block_id = models.PositiveIntegerField(null=True, blank=True)
    variable_id = models.PositiveIntegerField(null=True, blank=True)

    # We have two ways to order data. By time, and by sequential ID.
    # Not all records will have a sequential ID, but all should
    # eventually have a timestamp.
    # Store both the original device timestamp and the UTC date time.
    device_seqid = models.BigIntegerField(null=True, blank=True)
    device_timestamp = models.BigIntegerField(null=True, blank=True)
    timestamp = models.DateTimeField(null=True, blank=True)

    # Need to store a status enum to allow us to understand the state
    # of the data. This should be used less in the future, but was
    # important when data had to be committed and later modified.
    # TODO: Check if still needed
    status = models.CharField(max_length=3, choices=STATUS_CHOICES, default='unk')

    class Meta:
        abstract = True

    @property
    def _slugs(self):
        # returns a 'slug container' which contains every slug
        _slugs = type(
            'SlugsContainer',
            (object,),
            dict(project_slug=None, device_slug=None, variable_slug=None)
        )
        update_every_slug(_slugs, self)
        return _slugs

    @property
    def project_slug(self):
        return self._slugs.project_slug

    @property
    def device_slug(self):
        return self._slugs.device_slug

    @property
    def variable_slug(self):
        return self._slugs.variable_slug


class StreamTimeSeriesValue(StreamTimeSeries):
    """
    This is the main data table
    Represents a traditional numeric time series
    """

    type = models.CharField(max_length=3, choices=TYPE_CHOICES, default='Num')

    # New general purpose value for any type of numerical value
    # Assumes the Stream has a VarType defining the internal
    # units for the given type (e.g. 'Liters' for 'Volume')
    value = models.FloatField(null=True, blank=True)

    # raw_value is the old value that represented the raw
    # device value that the device is sending.
    # Depending on the sensor graph, this raw value will be
    # translated to self.value which represents data for a
    # given data type
    raw_value = models.BigIntegerField(null=True, blank=True)


class StreamTimeSeriesEvent(StreamTimeSeries):
    """
    Represents a time series with arbitrary JSON extra data
    """
    # We need a UUID to use on the s3 key. Cannot just use the record
    # id as the id is not known until after the record is
    # committed to the database, which is a problem with
    # kinesis firehose
    uuid = models.CharField(max_length=36, default=get_default_uuid, editable=False)
    s3_key_path = models.CharField(max_length=20, default='', null=True, blank=True)

    ext = models.CharField(max_length=10, choices=EXT_CHOICES, default='json', null=True, blank=True)

    # We want to have a json string with a key-value store to
    # allow us to store processed summary information related
    # to the event data.
    extra_data = models.JSONField(null=True, blank=True)

    # The format version determines how the bucket/key is computer
    #   - V1: Uses STREAM_EVENT_DATA_BUCKET_NAME and STREAM_EVENT_DATA_S3_KEY_FORMAT
    #   - V2: Uses its own self.s3_key_path instead of STREAM_EVENT_DATA_S3_KEY_FORMAT
    format_version = models.PositiveIntegerField(default=2)
