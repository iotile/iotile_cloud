from django.conf import settings

from apps.devicetemplate.models import DeviceTemplate
from .models import Project

def active_org(request):
    project = None
    template = None

    resolver_match = request.resolver_match
    if resolver_match:
        if 'project_id' in resolver_match.kwargs:
            project_id = resolver_match.kwargs['project_id']
            try:
                project = Project.objects.get(pk=project_id)
            except Project.DoesNotExist:
                pass

        if 'template_id' in resolver_match.kwargs:
            template_id = resolver_match.kwargs['template_id']
            template = DeviceTemplate.objects.get(pk=template_id)

    context = {
        'project': project,
        'template': template
    }

    return context