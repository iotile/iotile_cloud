import logging

from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.db.models import Manager
from django.db.models.signals import m2m_changed, post_save, pre_delete
from django.dispatch import receiver
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.org.models import Org
from apps.projecttemplate.models import ProjectTemplate
from apps.property.models import GenericProperty, GenericPropertyOrgTemplate
from apps.s3file.models import S3File
from apps.utils.gid.convert import gid2int
from apps.vartype.models import VarType, VarTypeInputUnit, VarTypeOutputUnit

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
logger = logging.getLogger(__name__)


class SensorGraphManager(Manager):
    """
    Manager to help with Project Management
    """

    def create_graph(self, org, created_by, name, active=True, report_processing_engine_ver=0, *args, **kwargs):
        sg = self.model(
            name=name,
            org=org,
            active=active,
            report_processing_engine_ver=report_processing_engine_ver,
            created_by=created_by
        )
        for key in kwargs:
            assert(hasattr(sg, key))
            setattr(sg, key, kwargs[key])

        sg.save()
        return sg

    def active_graphs(self):
        return self.filter(active=True)


class SensorGraph(models.Model):

    name = models.CharField(max_length=50)

    major_version = models.IntegerField(_('Major'), default=0)
    minor_version = models.IntegerField(_('Minor'), default=0)
    patch_version = models.IntegerField(_('Patch'), default=0)

    slug = models.SlugField(max_length=60, unique=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    # Organization that owns (made) the component
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='sensor_graphs', null=True, blank=True)
    active = models.BooleanField(default=True)

    # Each sensor graph should have a prefered roject template
    project_template = models.ForeignKey(ProjectTemplate, related_name='sensor_graphs',
                                         null=True, blank=True, on_delete=models.SET_NULL)

    # Streamer Report Processing Engine Version
    report_processing_engine_ver = models.PositiveIntegerField(default=0)

    # 20 bit number that indicates the sensor graph that the device is running.
    # There is an associated X.Y (8.4) version for the app
    # In general, for every SG.name, there should be a unique app_tag
    app_tag = models.PositiveIntegerField(_('App Tag'),  default=0)
    app_major_version = models.PositiveIntegerField(_('App Tag Major Ver'),  default=0)
    app_minor_version = models.PositiveIntegerField(_('App Tag Minor Ver'),  default=0)

    ui_extra = models.JSONField(null=True, blank=True)

    org_properties = models.ManyToManyField(GenericPropertyOrgTemplate, blank=True)

    # Master SG File
    sgf = models.OneToOneField(S3File, on_delete=models.SET_NULL, blank=True, null=True)

    description = models.TextField(_('Short Description'), blank=True)

    objects = SensorGraphManager()

    class Meta:
        ordering = ['name', 'major_version', 'minor_version', 'patch_version']
        unique_together = (('name', 'major_version', 'minor_version', 'patch_version'),)
        verbose_name = _("Sensor Graph")
        verbose_name_plural = _("Sensor Graphs")

    def __str__(self):
        return '{0} ({1})'.format(self.name, self.version)

    def save(self, *args, **kwargs):
        name = '{0}--v{1}-{2}-{3}'.format(self.name,
                                          self.major_version,
                                          self.minor_version,
                                          self.patch_version)
        self.slug = slugify(name)
        super(SensorGraph, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('sensor-graph:detail', args=(self.slug,))

    def get_edit_ui_extra_url(self):
        return reverse('sensor-graph:edit-ui-extra', args=(self.slug,))

    def get_edit_sgf_url(self):
        return reverse('sensor-graph:edit-sgf', args=(self.slug,))

    @property
    def version(self):
        return 'v{0}.{1}.{2}'.format(self.major_version, self.minor_version, self.patch_version)

    @property
    def app_version(self):
        return 'v{}.{}'.format(self.app_major_version, self.app_minor_version)

    @property
    def app_tag_and_version(self):
        return '{} v{}.{}'.format(self.app_tag, self.app_major_version, self.app_minor_version)

    def is_owner(self, user):
        if user.is_anonymous:
            return False
        if user.is_staff:
            return True

        if self.org:
            return self.org.has_access(user)

        return False

    def has_access(self, user):
        if user.is_staff:
            return True

        if not self.active and self.org:
            # If not active, only Owner Org can see it
            return self.org.has_access(user)

        return user == self.created_by

    def has_write_access(self, user):
        if user.is_staff:
            return True

        if self.org:
            # If not active, only Owner Org can see it
            return self.org.has_access(user)

        return False


class VariableTemplate(models.Model):
    label = models.CharField(_('Label'), max_length=60, default='', blank=True)
    sg = models.ForeignKey('SensorGraph', on_delete=models.CASCADE, related_name='variable_templates')

    lid_hex = models.CharField(_('Local Variable ID'), max_length=4, default='')
    derived_lid_hex = models.CharField(_('Derived Local Variable ID'), max_length=4, default='', blank=True)
    var_type = models.ForeignKey(VarType, on_delete=models.CASCADE,
                                 related_name='variable_templates', null=True, blank=True)

    # Required MDO to convert this unit to the to the raw unit in the VarType
    m = models.IntegerField(default=1)
    d = models.IntegerField(default=1)
    o = models.FloatField(default=0.0)

    ctype = models.CharField(max_length=16, default='unsigned int')

    default_input_unit = models.ForeignKey(VarTypeInputUnit, null=True, blank=True, on_delete=models.SET_NULL)
    default_output_unit = models.ForeignKey(VarTypeOutputUnit, null=True, blank=True, on_delete=models.SET_NULL)

    app_only = models.BooleanField(default=False)
    web_only = models.BooleanField(default=False)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['sg', 'lid_hex',]
        verbose_name = _('Variable Template')
        verbose_name_plural = _('Variable Templates')

    def __str__(self):
        return 'VT{0} - {1} : {2}'.format(self.id, self.sg_id, self.label)

    @property
    def lid(self):
        return gid2int(self.lid_hex)


class DisplayWidgetTemplate(models.Model):
    TYPE_CHOICES = (('val', 'Data Stream Value'),
                    ('btn', 'Default Button'),
                    ('sbt', 'Switch Button'))

    label = models.CharField(_('Label'), max_length=60, default='', blank=True)
    sg = models.ForeignKey('SensorGraph', on_delete=models.CASCADE, related_name='display_widget_templates')

    lid_hex = models.CharField(_('Local Variable ID'), max_length=4, default='')
    var_type = models.ForeignKey(VarType, on_delete=models.CASCADE,
                                 related_name='display_widget_templates', null=True, blank=True)

    # Each output_unit has a derived_output JSON, which allows for a secondary conversion,
    # usually to convert into time base rates. It is formatted as
    #   { "someType": { "derived1": {"m": 2, "d": 3 }, "derived2": {"m": 1, "d": 1}}
    # derived_unit_type represents the "someType". e.g. "Rate" or "Flow"
    derived_unit_type = models.CharField(max_length=20, default='', blank=True)

    show_in_app = models.BooleanField(default=False)
    show_in_web = models.BooleanField(default=False)

    type = models.CharField(max_length=4, choices=TYPE_CHOICES, default='val')
    args = models.JSONField(null=True, blank=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['sg', 'lid_hex',]
        verbose_name = _('Display Widget')
        verbose_name_plural = _('Display Widgets')

    def __str__(self):
        return 'DW{0} - {1} : {2}'.format(self.id, self.sg_id, self.label)


class GenericPropertyTemplate(models.Model):
    """
    This model is no longer used.
    It has been replaced by GenericPropertyOrgTemplate.
    """

    name = models.CharField(max_length=40)

    class Meta:
        ordering = ['name']
        verbose_name = _("Property Template")
        verbose_name_plural = _("Property Templates")


def _clear_sg_api_cache():
    key = 'views.decorators.cache.cache_page.api:sg.*'
    try:
        cache.delete_pattern(key)
    except Exception:
        logger.warning('Cannot delete cache: delete_pattern not available')


@receiver(pre_delete, sender=SensorGraph, dispatch_uid="sensor_graph_pre_delete_signal")
def sensor_graph_pre_delete_receiver(sender, **kwargs):
    _clear_sg_api_cache()


@receiver(m2m_changed, sender=SensorGraph.org_properties.through, dispatch_uid="org_property_template_m2m_signal")
def org_property_template_m2m_change(sender, **kwargs):
    _clear_sg_api_cache()


@receiver(post_save, sender=SensorGraph, dispatch_uid="sensor_graph_post_save_signal")
def sensor_graph_post_save_receiver(sender, **kwargs):
    _clear_sg_api_cache()


@receiver(pre_delete, sender=DisplayWidgetTemplate, dispatch_uid="display_widget_pre_delete_signal")
def display_widget_pre_delete_receiver(sender, **kwargs):
    _clear_sg_api_cache()


@receiver(post_save, sender=DisplayWidgetTemplate, dispatch_uid="display_widget_post_save_signal")
def display_widget_post_save_receiver(sender, **kwargs):
    _clear_sg_api_cache()


@receiver(pre_delete, sender=VariableTemplate, dispatch_uid="variable_template_pre_delete_signal")
def variable_template_pre_delete_receiver(sender, **kwargs):
    _clear_sg_api_cache()


@receiver(post_save, sender=VariableTemplate, dispatch_uid="variable_template_post_save_signal")
def variable_template_post_save_receiver(sender, **kwargs):
    _clear_sg_api_cache()
