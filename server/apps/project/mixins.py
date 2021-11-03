from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from apps.configattribute.models import ConfigAttribute
from apps.org.roles import NO_PERMISSIONS_ROLE

from .models import Project


def get_project_menu_extras(project):
    """
    Check if there are any Config Attributes for extra project side menus
    :param project: Project Object
    :return: Array of objects of the form:
        {
          "url": "/apps/shipping/p--0000-0015/sxd/device/",
          "icon": "fa fa-cloud-upload",
          "label": "SXd Uploader"
        }
    """
    config_name = ':classic:menus:project:extras'
    config_attr = ConfigAttribute.objects.get_attribute(name=config_name, target=project)
    if config_attr:
        return config_attr.data
    return None


class ProjectBaseAccessMixin(object):

    def get_basic_context(self, project):

        if project:
            context = {
                'project': project,
                'org': project.org
            }

            if project.org:
                context.update(project.org.permissions(self.request.user))
            else:
                context.update(NO_PERMISSIONS_ROLE)

            context['project_menu_extras'] = get_project_menu_extras(project)

            return context

        return NO_PERMISSIONS_ROLE

    def get_project(self, key='pk'):

        object = get_object_or_404(Project, pk=self.kwargs[key])
        if object.org.has_permission(self.request.user, 'can_access_classic'):
            return object

        raise PermissionDenied('User has no read permission to Project {}'.format(object.slug))

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(ProjectBaseAccessMixin, self).dispatch(request, *args, **kwargs)

