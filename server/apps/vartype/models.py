import logging
import uuid

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.cache import cache
from django.db import models
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.utils.mdo.helpers import MdoHelper

from .types import STREAM_DATA_TYPE_CHOICES

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
logger = logging.getLogger(__name__)


class VarType(models.Model):
    """
    Represents the type of variable used to store stream data/events
    Depending on the variable type, data is stored on the database
    in a particular way. For example, data representing liquid may be
    stored with VarType=Volume, which stores data in liters.

    VarType objects have associated input and output units, which represent
    the acceptable transformations. For example, for volume, we may accept
    Gallons, Liters, and Barrels as inputs. The InputUnits stores the appropriate
    MDO to transform those different units to the required liters we use for storing.
    In a similar way, the user may request to visualize the data in gallons, or barrels,
    so the OutputUnits has the required MDO to make those transformations.

    Some streams represent simple time series with a single value per record (StreamData)
    while others represent more complex data (StreamEventData), which can contain both
    unstructured data (event.extra_data) and/or some kind of attached file (event.data)

    In some cases, data is stored in more complicated ways:

    - Data is encoded as a StreamData stream, where a decoder is used to decode that data
      and create StreamEvents from it. In this case, both a VarTypeDecoder and VarTypeSchema is used

    - Data is loaded into StreamEventData records, but for each of these events, an associated
      StreamData record is stored. This data record contains the incremental_id for the event.
    """

    slug = models.SlugField(max_length=30, unique=True)

    # e.g. 'Liquid Flow', 'Liquid Volume'
    name = models.CharField(max_length=26, unique=True)
    # 'Kilo Liters', 'percent'
    storage_units_full = models.CharField(max_length=26, default='', blank=True)

    # This helps us determnte if the stream has an associated StreamData, StreamEvent or both
    stream_data_type = models.CharField(_('Data Type'), max_length=2, choices=STREAM_DATA_TYPE_CHOICES, default='00')

    # True if VarType has associated VarTypeDecoder record
    # This decoder is used to transform data encoded in multiple data records into a
    # single StreamEventData record
    is_encoded = models.BooleanField(default=False)
    # True if VarType has associated VarTypeSchema record.
    # This schema is used to help process any StreamEventData.extra_data JSON object
    has_schema = models.BooleanField(default=False)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['slug']
        verbose_name = _('Variable Type')
        verbose_name_plural = _('Variable Types')

    def save(self, *args, **kwargs):
        self.slug = slugify(self.name)
        super(VarType, self).save(*args, **kwargs)

    def __str__(self):
        return '{0}'.format(self.name)

    def get_absolute_url(self):
        return reverse('var-type:detail', args=(self.slug,))

    def has_edit_access(self, user):
        return user.is_staff


class VarTypeUnit(models.Model):

    slug = models.SlugField(max_length=54, unique=True)

    # e.g. 'Gallons', 'Liters'
    unit_full = models.CharField(max_length=20)
    # e.g. 'G', 'L'
    unit_short = models.CharField(max_length=5, default='', blank=True)

    # Required MDO to convert this unit to the to the raw unit in the VarType
    m = models.IntegerField(default=1)
    d = models.IntegerField(default=1)
    o = models.FloatField(default=0.0)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        abstract = True

    def __str__(self):
        return self.unit_full

    def has_edit_access(self, user):
        return user.is_staff

    def get_mdo_helper(self):
        return MdoHelper(m=self.m, d=self.d, o=self.o)


class VarTypeInputUnit(VarTypeUnit):

    var_type = models.ForeignKey('VarType', on_delete=models.CASCADE, related_name='input_units')

    class Meta:
        ordering = ['slug']
        unique_together = (('var_type', 'unit_full'),)
        verbose_name = _('Input Unit')
        verbose_name_plural = _('Input Units')

    def save(self, *args, **kwargs):
        self.slug = '--'.join(['in', self.var_type.slug, slugify(self.unit_full)])
        super(VarTypeInputUnit, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('var-type:in-unit', args=(self.slug,))


class VarTypeOutputUnit(VarTypeUnit):

    var_type = models.ForeignKey('VarType', on_delete=models.CASCADE, related_name='output_units')
    decimal_places = models.IntegerField(default=0)
    # Derived Units are used to represent simple derivations.
    # Adding time to a Unit is a good example (Volume -> Flow)
    # Deerived Units should be represented JSON, as a Dictionary of Dictionaries
    # where the first level is the type of derivation followed by the actual derivations
    # Each object (actual derivation) stores an MDO
    # e.g.
    #   { "someType": { "derived1": {"m": 2, "d": 3 }, "derived2": {"m": 1, "d": 1}}
    derived_units = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['slug']
        unique_together = (('var_type', 'unit_full'),)
        verbose_name = _('Output Unit')
        verbose_name_plural = _('Output Units')

    def save(self, *args, **kwargs):
        self.slug = '--'.join(['out', self.var_type.slug, slugify(self.unit_full)])
        super(VarTypeOutputUnit, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('var-type:out-unit', args=(self.slug,))


class VarTypeDecoder(models.Model):

    var_type = models.OneToOneField(VarType, on_delete=models.CASCADE, related_name='decoder')

    # Data encoding if StreamData is encoded
    raw_packet_format = models.CharField(max_length=32, default='')

    packet_info = models.JSONField(null=True, blank=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['var_type', 'created_on', 'id']
        verbose_name = _('Variable Type Decoder')
        verbose_name_plural = _('Variable Type Decoders')

    def __str__(self):
        return '{0} ({1})'.format(self.id, self.raw_packet_format)


class VarTypeSchema(models.Model):

    var_type = models.OneToOneField(VarType, on_delete=models.CASCADE, related_name='schema')

    # keys represents the keys in the StreamEventData.extra_data dictionary
    keys = models.JSONField(null=True, blank=True)
    display_order = ArrayField(models.CharField(max_length=64), blank=True, default = list)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['var_type', 'created_on', 'id']
        verbose_name = _('Variable Type Schema')
        verbose_name_plural = _('Variable Type Schema')

    def __str__(self):
        return 'Schema{0} (vt id={1})'.format(self.id, self.var_type_id)


def delete_serialized_unit_cache(slug):
    if cache:
        logger.info('VarTypeUnit: cache(DELETE)={0}'.format(slug))
        cache.delete(slug)

        key = 'views.decorators.cache.cache_page.api:vartype.*'
        try:
            cache.delete_pattern(key)
        except Exception:
            logger.warning('Cannot delete VarType API cache: delete_pattern not available')


@receiver(post_save, sender=VarTypeInputUnit)
def post_save_var_type_input_unit_callback(sender, **kwargs):
    unit = kwargs['instance']
    logger.info('post-save-state: {0}'.format(unit.slug))
    delete_serialized_unit_cache(unit.slug)


@receiver(pre_delete, sender=VarTypeInputUnit)
def pre_delete_var_type_input_unit_callback(sender, **kwargs):
    unit = kwargs['instance']
    logger.info('pre-delete: {0}'.format(unit.slug))
    delete_serialized_unit_cache(unit.slug)


@receiver(post_save, sender=VarTypeOutputUnit)
def post_save_var_type_output_unit_callback(sender, **kwargs):
    unit = kwargs['instance']
    logger.info('post-save-state: {0}'.format(unit.slug))
    delete_serialized_unit_cache(unit.slug)


@receiver(pre_delete, sender=VarTypeOutputUnit)
def pre_delete_var_type_output_unit_callback(sender, **kwargs):
    unit = kwargs['instance']
    logger.info('pre-delete: {0}'.format(unit.slug))
    delete_serialized_unit_cache(unit.slug)


@receiver(pre_delete, sender=VarType, dispatch_uid="var_type_pre_delete_signal")
def var_type_pre_delete_receiver(sender, **kwargs):
    key = 'views.decorators.cache.cache_page.api:vartype.*'
    try:
        cache.delete_pattern(key)
    except:
        logger.warning('Cannot delete VarType API cache: delete_pattern not available')


@receiver(post_save, sender=VarType, dispatch_uid="var_type_post_save_signal")
def var_type_post_save_receiver(sender, **kwargs):
    key = 'views.decorators.cache.cache_page.api:vartype.*'
    try:
        cache.delete_pattern(key)
    except:
        logger.warning('Cannot delete VarType API cache: delete_pattern not available')


@receiver(pre_delete, sender=VarTypeDecoder, dispatch_uid="var_type_decoder_pre_delete_signal")
def var_type_decoder_pre_delete_receiver(sender, **kwargs):
    key = 'views.decorators.cache.cache_page.api:vartype.*'
    try:
        cache.delete_pattern(key)
    except:
        logger.warning('Cannot delete VarType API cache: delete_pattern not available')

    decoder = kwargs['instance']
    logger.info('pre_delete: {0} with {1}'.format(decoder.id, decoder.var_type))
    var_type = decoder.var_type
    var_type.is_encoded = False
    var_type.save()


@receiver(post_save, sender=VarTypeDecoder, dispatch_uid="var_type_decoder_post_save_signal")
def var_type_decoder_post_save_receiver(sender, **kwargs):
    key = 'views.decorators.cache.cache_page.api:vartype.*'
    try:
        cache.delete_pattern(key)
    except:
        logger.warning('Cannot delete VarType API cache: delete_pattern not available')

    decoder = kwargs['instance']
    logger.info('post_save: {0} with {1}'.format(decoder.id, decoder.var_type))
    var_type = decoder.var_type
    var_type.is_encoded = True
    var_type.save()


@receiver(pre_delete, sender=VarTypeSchema, dispatch_uid="var_type_schema_pre_delete_signal")
def var_type_schema_pre_delete_receiver(sender, **kwargs):
    key = 'views.decorators.cache.cache_page.api:vartype.*'
    try:
        cache.delete_pattern(key)
    except:
        logger.warning('Cannot delete VarType API cache: delete_pattern not available')

    schema = kwargs['instance']
    logger.info('pre_delete: {0} with {1}'.format(schema.id, schema.var_type))
    var_type = schema.var_type
    var_type.has_schema = False
    var_type.save()


@receiver(post_save, sender=VarTypeSchema, dispatch_uid="var_type_schema_post_save_signal")
def var_type_schema_post_save_receiver(sender, **kwargs):
    key = 'views.decorators.cache.cache_page.api:vartype.*'
    try:
        cache.delete_pattern(key)
    except:
        logger.warning('Cannot delete VarType API cache: delete_pattern not available')

    schema = kwargs['instance']
    logger.info('post_save: {0} with {1}'.format(schema.id, schema.var_type))
    var_type = schema.var_type
    var_type.has_schema = True
    var_type.save()

