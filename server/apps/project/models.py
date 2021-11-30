import logging
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Manager, Max
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from iotile_cloud.utils.gid import IOTileStreamSlug, IOTileVariableSlug

from apps.org.models import Org
from apps.projecttemplate.models import ProjectTemplate
from apps.property.models import GenericProperty
from apps.utils.gid.convert import formatted_gpid, int2pid

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
logger = logging.getLogger(__name__)


class ProjectManager(Manager):
    """
    Manager to help with Device Management
    """

    def get_from_request(self, request):
        resolver_match = request.resolver_match
        if resolver_match:
            if 'project_id' in resolver_match.kwargs:
                project_id = resolver_match.kwargs['project_id']
                project = get_object_or_404(self.model, pk=project_id)
                return project

        return None

    def user_project_qs(self, user):
        orgs = Org.objects.user_orgs_ids(user)
        return Project.objects.filter(is_template=False, org__in=orgs).select_related('org')

    def master_project_for_template(self, project_template):
        if project_template:
            projects = project_template.projects.filter(is_template=True)
            if projects:
                return projects.first()
        return None


class Project(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gid = models.PositiveIntegerField(default=0, editable=False)
    name = models.CharField(max_length=50, unique=False)
    slug = models.SlugField(max_length=30, unique=False)
    about = models.TextField(blank=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_projects')
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='projects', null=True, blank=True)

    # Projects are created from project_templates
    # But a ProjectTemplate itself has one and only one Project that represents
    # the Template itself. That project can be found by searching for
    #      filter(project_template=template, is_template=True)
    # And all projects that actually derive from the Template are:
    #      filter(project_template=template, is_template=False)
    is_template = models.BooleanField(default=False)
    project_template = models.ForeignKey(ProjectTemplate, related_name='projects',
                                         null=True, blank=True, on_delete=models.SET_NULL)

    objects = ProjectManager()

    class Meta:
        ordering = ['org', 'name']
        verbose_name = _("Project")
        verbose_name_plural = _("Projects")

    def __str__(self):
        if self.org_id:
            return '{0} - {1}'.format(self.org.name, self.name)
        else:
            return 'NoOrg - {0}'.format(self.name)

    @property
    def formatted_gid(self):
        return int2pid(self.gid)

    @property
    def obj_target_slug(self):
        return self.slug

    def save(self, *args, **kwargs):
        if not self.gid:
            stats = Project.objects.all().aggregate(Max('gid'))
            if stats and 'gid__max' in stats and stats['gid__max']:
                self.gid = stats['gid__max'] + 1
            else:
                self.gid = 1
        self.slug = formatted_gpid(pid=self.formatted_gid)
        super(Project, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('org:project:detail', args=(str(self.org.slug), str(self.id),))

    def get_notes_url(self):
        return reverse('streamnote:list', args=(self.slug,))

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

    def get_webapp_url(self):
        """
        Get URL for specific project page in WebApp
        e.g.
        https://app-stage.iotile.cloud/#/projects/63a4abe5-9c54-4c46-9df9-d116df37a5d9
        :return: Absolute URL including domain
        """
        domain = getattr(settings, 'WEBAPP_BASE_URL')
        if self.project_template and 'Shipping' in self.project_template.name:
            return '{0}/#/shipping/project/{1}'.format(domain, str(self.id))
        return '{0}/#/projects/{1}'.format(domain, str(self.id))

    def get_properties_qs(self):
        """
        Query for all properties associated with this project slug
        :return: queryset
        """
        return GenericProperty.objects.object_properties_qs(self)

    def get_property_url(self):
        """
        Redirect url for GenericProperty views for this project
        """
        return reverse('org:project:property', kwargs={'org_slug': self.org.slug, 'pk': self.id})

    def get_variable_slug_for(self, variable):
        return IOTileVariableSlug(id=variable, project=self.slug)

    def get_stream_slug_for(self, variable):
        stream_slug = IOTileStreamSlug()
        stream_slug.from_parts(project=self.slug, device=0, variable=variable)
        return stream_slug


@receiver(post_save, sender=Project)
def post_save_streamid_callback(sender, **kwargs):
    project = kwargs['instance']
    created = kwargs['created']
    if created:
        # CRITICAL. Make sure you do not create an infinite loop with the save()
        project.slug = formatted_gpid(pid=project.formatted_gid)
        project.save()


@receiver(post_save, sender=ProjectTemplate)
def post_save_project_callback(sender, **kwargs):
    template = kwargs['instance']
    created = kwargs['created']
    if created:
        master_project = Project.objects.create(
            name=template.name,
            project_template=template,
            org=template.org,
            created_by=template.created_by,
            is_template=True
        )
        logger.debug('created master project: {0}'.format(master_project))

