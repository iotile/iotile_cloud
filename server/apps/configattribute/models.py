import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.utils.objects.utils import get_object_by_slug

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
logger = logging.getLogger(__name__)


def validate_config_name(value):
    if value[0] != ':':
        raise ValidationError(
            f'Name must start with ":". Got: {value}'
        )
    if ' ' in value:
        raise ValidationError(
            f'Name cannot have spaces. Got: {value}'
        )


def validate_config(value):
    if value[0] not in ['^', '@', 'd', 'p', 'b', ]:
        raise ValidationError(
            f'Target must start with ^, @, d, p, or b. Got: {value}'
        )
    if ' ' in value:
        raise ValidationError(
            'Target cannot have spaces. Got: {value}'
        )


def get_or_create_config_name(name):
    """
    Get the ConfigAttributeName object for the given name.
    If it does not exist, create one.
    All configuration names shold exist in production, but it is harmless 
    to create one if it does not exist, so do so.
    """
    try:
        obj = ConfigAttributeName.objects.get(name=name)
    except ConfigAttributeName.DoesNotExist:
        # This is mostly for development as all names should be created in production
        user_model = get_user_model()
        logger.warning('Creating new ConfigAttribute: {}'.format(name))
        obj = ConfigAttributeName.objects.create(name=name, created_by=user_model.objects.get_admin())
    return obj


class ConfigAttributeManager(models.Manager):
    """
    Manager to help with ConfigAttributes Management
    """

    def _config_name(self, name, updated_by=None):
        if not isinstance(name, ConfigAttributeName):
            try:
                return ConfigAttributeName.objects.get(name=name)
            except ConfigAttributeName.DoesNotExist:
                if updated_by:
                    return ConfigAttributeName.objects.create(name=name, created_by=updated_by)
                return None
        return name

    def get_or_create_attribute(self, target, name, data, updated_by):
        """

        :param target: Obj to associate configuration with
        :param name: str or ConfigAttributeName for configuration attribute name
        :param data: JSON with data to store. If existing obj, data will be overwriten with this new data
        :param updated_by: Owner
        :return: Existing obj with same name/target or new obj
        """

        name = self._config_name(name, updated_by)

        slug = target.obj_target_slug
        obj, created = self.get_or_create(
            target=slug,
            name=name,
            defaults={
                'data': data,
                'updated_by': updated_by
            }
        )

        if not created:
            obj.data = data
            obj.save()

        return obj

    def clone(self, src, target_slug):
        """
        Copy the object and assign to a new target
        :param src: ConfigAttribute to copy from
        :param target_slug: Slug of new target
        :return: new obj
        """
        obj = self.model(
            target=target_slug,
            name=src.name,
            data=src.data,
            updated_by=src.updated_by
        )
        obj.save()
        return obj

    def get_attribute_by_slug(self, target_slug, name):

        name = self._config_name(name)

        try:
            return self.model.objects.get(target=target_slug, name=name)
        except self.model.DoesNotExist:
            return None

    def get_attribute(self, target, name):

        target_slug = target.obj_target_slug
        return self.get_attribute_by_slug(target_slug, name)

    def qs_by_target(self, target):
        target_slug = target.obj_target_slug
        return self.model.objects.filter(target=target_slug)

    def get_attribute_by_priority(self, target_slug, name, user=None):
        """
        Get config attribute associated to this target, or if not found, search higher priority objects
        until an attribute with the same name is found. For example, if attribute is requested on a
        project, and not found, it will contibute to search or its org and if not found, its user

        :param target_slug: globally unique target (using obj.obj_target_slug) to begin search path
        :param name: str or ConfigAttributeName for configuration attribute name
        :param user: User that is requesting information. Important as configuration may be assigned per user
        :return: obj
        """

        name = self._config_name(name)

        next_item = {
            'device': lambda obj, user: obj.project,
            'project': lambda obj, user: obj.org,
            'datablock': lambda obj, user: obj.org,
            'org': lambda obj, user: user,
            'user': lambda obj, user: None,
        }
        while target_slug:
            obj_type, target = get_object_by_slug(target_slug)
            if target:
                target_slug = None
                try:
                    return self.model.objects.get(target=target.obj_target_slug, name=name)
                except self.model.DoesNotExist:
                    if obj_type in next_item:
                        target = next_item[obj_type](target, user)
                        if target:
                            target_slug = target.obj_target_slug

        return None


class ConfigAttributeName(models.Model):

    name = models.CharField(max_length=64, unique=True, validators=[validate_config_name])
    description = models.TextField(blank=True, null=True)
    tags = ArrayField(models.CharField(max_length=24), blank=True, default = list)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['name']
        verbose_name = _("Configuration Attribute Name")
        verbose_name_plural = _("Configuration Attribute Names")

    def __str__(self):
        return self.name


class ConfigAttribute(models.Model):
    """
    Configuration Attribute records are used to store any information we want to associate with a given
    User, Org, Project or any other object, as long as the object has a obj_target_slug property able
    to create a globally unique string
    """

    target = models.CharField(max_length=64, validators=[validate_config])

    name = models.ForeignKey(ConfigAttributeName, on_delete=models.CASCADE)
    data = models.JSONField(null=True, blank=True)

    updated_on = models.DateTimeField('update_on', auto_now=True)
    updated_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    objects = ConfigAttributeManager()

    class Meta:
        ordering = ['target', 'name']
        unique_together = (('target', 'name', ),)
        verbose_name = _("Configuration Attribute")
        verbose_name_plural = _("Configuration Attributes")

    @property
    def obj(self):
        n, o = get_object_by_slug(self.target)
        return o

    def __str__(self):
        return ':'.join([self.target, str(self.name)])

    def get_edit_url(self):
        return reverse('config-attribute:edit', args=(self.id,))
