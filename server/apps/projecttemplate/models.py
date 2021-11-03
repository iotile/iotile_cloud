import uuid
from django.db import models
from django.conf import settings
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.db.models import Manager

from apps.org.models import Org
from apps.utils.gid.convert import int2pid

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')


class ProjectTemplateManager(Manager):
    """
    Manager to help with Project Template
    """

    def create_template(self, org, created_by, name, active=True,
                        major_version=0, minor_version=0, patch_version=0):
        template = self.model(
            name=name,
            org=org,
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


class ProjectTemplate(models.Model):

    name = models.CharField(max_length=50)

    major_version = models.IntegerField(_('Major'), default=0)
    minor_version = models.IntegerField(_('Minor'), default=0)
    patch_version = models.IntegerField(_('Patch'), default=0)

    slug = models.SlugField(max_length=60, unique=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    # Organization that owns (made) the template
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='project_templates', null=True, blank=True)
    active = models.BooleanField(default=True)

    # Template configuration. Use this field to store UI or other information
    extra_data = models.JSONField(null=True, blank=True)

    objects = ProjectTemplateManager()

    class Meta:
        ordering = ['name', 'major_version', 'minor_version', 'patch_version']
        unique_together = (('name', 'major_version', 'minor_version', 'patch_version'),)
        verbose_name = _("Project Template")
        verbose_name_plural = _("Project Templates")

    def __str__(self):
        if self.org:
            return '{0} - {1}'.format(self.org, self.name)
        return '{0} - {1}'.format(self.name, self.version)

    def save(self, *args, **kwargs):
        name = '{0}--v{1}-{2}-{3}'.format(self.name,
                                          self.major_version,
                                          self.minor_version,
                                          self.patch_version)
        self.slug = slugify(name)
        super(ProjectTemplate, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('project-template:detail', args=(self.slug,))

    @property
    def formatted_gid(self):
        return int2pid(self.id)

    @property
    def version(self):
        return 'v{0}.{1}.{2}'.format(self.major_version, self.minor_version, self.patch_version)

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

