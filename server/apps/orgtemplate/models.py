import uuid

from django.conf import settings
from django.db import models
from django.db.models import Manager
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')


class OrgTemplateManager(Manager):
    """
    Manager to help with Org Templates
    """

    def create_template(self, created_by, name, active=True,
                        major_version=0, minor_version=0, patch_version=0):
        template = self.model(
            name=name,
            active=active,
            major_version=major_version,
            minor_version=minor_version,
            patch_version=patch_version,
            created_by=created_by
        )
        template.save()
        return template

    def active_templates(self):
        return self.filter(active=True)

    def get_from_request(self, request):
        resolver_match = request.resolver_match
        if resolver_match:

            if 'template_id' in resolver_match.kwargs:
                template_id = resolver_match.kwargs['template_id']

                return self.model.objects.get(pk=template_id)

        return None


class OrgTemplate(models.Model):

    name = models.CharField(max_length=50)

    major_version = models.IntegerField(_('Major'), default=0)
    minor_version = models.IntegerField(_('Minor'), default=0)
    patch_version = models.IntegerField(_('Patch'), default=0)

    slug = models.SlugField(max_length=60, unique=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    active = models.BooleanField(default=True)

    # Template configuration. Use this field to store UI or other information
    extra_data = models.JSONField(null=True, blank=True)

    objects = OrgTemplateManager()

    class Meta:
        ordering = ['name', 'major_version', 'minor_version', 'patch_version']
        unique_together = (('name', 'major_version', 'minor_version', 'patch_version'),)
        verbose_name = _("Org Template")
        verbose_name_plural = _("Org Templates")

    def __str__(self):
        return '{0} - {1}'.format(self.name, self.version)

    def save(self, *args, **kwargs):
        name = '{0}--v{1}-{2}-{3}'.format(self.name,
                                          self.major_version,
                                          self.minor_version,
                                          self.patch_version)
        self.slug = slugify(name)
        super(OrgTemplate, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('org-template:detail', args=(self.slug,))

    @property
    def version(self):
        return 'v{0}.{1}.{2}'.format(self.major_version, self.minor_version, self.patch_version)

    def is_owner(self, user):
        if user.is_anonymous:
            return False
        return user.is_staff

    def has_access(self, user):
        if user.is_staff:
            return True

        return user == self.created_by

    def has_write_access(self, user):
        return user.is_staff

