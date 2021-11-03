import logging
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from apps.utils.objects.utils import get_object_by_slug
from apps.org.models import Org

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
logger = logging.getLogger(__name__)

PROPERTY_TYPE_CHOICES = (
    ('int', 'Integer'),
    ('str', 'String'),
    ('bool', 'Boolean'),
)


class GenericPropertyManager(models.Manager):
    """
    Manager to help with GenericProperty Management
    """

    def _create_property(self, slug, name, created_by, is_system):
        obj = self.model(
            target=slug,
            name=name,
            is_system=is_system,
            created_by=created_by
        )
        return obj

    def create_int_property(self, slug, name, value, created_by, is_system=False):
        obj = self._create_property(slug, name, created_by, is_system)
        obj.set_int_value(value)
        obj.save()
        return obj

    def create_str_property(self, slug, name, value, created_by, is_system=False):
        obj = self._create_property(slug, name, created_by, is_system)
        obj.set_str_value(value)
        obj.save()
        return obj

    def create_bool_property(self, slug, name, value, created_by, is_system=False):
        obj = self._create_property(slug, name, created_by, is_system)
        obj.set_bool_value(value)
        obj.save()
        return obj

    def clone(self, src, target_slug):
        obj = self.model(
            target=target_slug,
            name=src.name,
            str_value=src.str_value,
            type=src.type,
            is_system=src.is_system,
            created_by=src.created_by
        )
        obj.save()
        return obj

    def object_property(self, obj, name):
        slug = obj.slug
        try:
            return self.model.objects.get(target=slug, name=name)
        except GenericProperty.DoesNotExist:
            return None

    def object_properties_qs(self, obj, is_system=None):
        slug = obj.slug
        if is_system is None:
            return self.model.objects.filter(target=slug)
        return self.model.objects.filter(target=slug, is_system=is_system)

    def create_update_or_delete_str_value(self, target, name, value, updated_by):
        if isinstance(value, GenericPropertyOrgEnum):
            value = value.value
        if value:
            try:
                gp = GenericProperty.objects.get(
                    target=target,
                    name=name
                )
                gp.set_str_value(value)
                gp.creayed_by = updated_by
                gp.save()
            except GenericProperty.DoesNotExist:
                GenericProperty.objects.create_str_property(
                    slug=target,
                    name=name,
                    value=value,
                    created_by=updated_by
                )
        else:
            try:
                gp = GenericProperty.objects.get(
                    target=target,
                    name=name
                )
                gp.delete()
            except GenericProperty.DoesNotExist:
                pass


class GenericPropertyOrgTemplate(models.Model):

    type = models.CharField(max_length=4, choices=PROPERTY_TYPE_CHOICES, default='str')
    name = models.CharField(max_length=48)
    default = models.CharField(max_length=256, default='', blank=True)

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='property_defaults')

    extra = models.JSONField(null=True, blank=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['org', 'name']
        unique_together = (('org', 'name'),)
        verbose_name = _("Property Org Template")
        verbose_name_plural = _("Property Org Templates")

    def __str__(self):
        return '{0} - {1}'.format(self.org, self.name)

    def get_absolute_url(self):
        return reverse('property:template-detail', args=(self.org.slug, self.id,))


class GenericPropertyOrgEnum(models.Model):

    value = models.CharField(max_length=64)
    template = models.ForeignKey(GenericPropertyOrgTemplate, on_delete=models.CASCADE, related_name='enums')

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='property_enums')

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['template', 'value']
        unique_together = (('template', 'value'),)
        verbose_name = _("Property Org Enum Value")
        verbose_name_plural = _("Property Org Enum Values")

    def __str__(self):
        return '{0} - {1} = {2}'.format(self.org, self.template.name, self.value)


class GenericProperty(models.Model):
    target = models.SlugField(max_length=42)
    type = models.CharField(max_length=4, choices=PROPERTY_TYPE_CHOICES, default='str')
    name = models.CharField(max_length=40)
    str_value = models.CharField(max_length=256, default='', blank=True)

    is_system = models.BooleanField(default=False, blank=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    objects = GenericPropertyManager()

    class Meta:
        ordering = ['target', 'name']
        unique_together = (('target', 'name', ),)
        verbose_name = _("Property")
        verbose_name_plural = _("Properties")

    @property
    def value(self):
        if self.type == 'int':
            return int(self.str_value)
        if self.type == 'bool':
            return self.str_value == 'True'
        return self.str_value

    @property
    def obj(self):
        _, o = get_object_by_slug(self.target)
        return o

    def set_int_value(self, value):
        assert isinstance(value, int), 'Value {} is not a int'.format(value)
        self.str_value = str(value)
        self.type = 'int'

    def set_str_value(self, value):
        assert isinstance(value, str), 'Value {} is not a str'.format(value)
        if len(value) > 256:
            # Ensure we do not go over field size limit
            value = value[0:255]
        self.str_value = value
        self.type = 'str'

    def set_bool_value(self, value):
        assert isinstance(value, bool), 'Value {} is not a bool'.format(value)
        self.str_value = str(value)
        self.type = 'bool'
