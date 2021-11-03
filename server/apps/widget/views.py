from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.views.generic import DetailView
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied

from apps.physicaldevice.models import Device
from apps.stream.models import StreamVariable

from .models import *

class PageDeviceAccessMixin(object):

    def get_object(self, queryset=None):

        object = get_object_or_404(Device, slug=self.kwargs['slug'])
        if object.has_access(self.request.user):
            return object

        raise PermissionDenied("User has no access to this IOTile Device")


class PageDeviceView(PageDeviceAccessMixin, DetailView):
    model = Device
    page = None

    def get_template_names(self):

        # No longer support widget pages, so just assume default page
        return 'widget/page/default/page.html'

    def get_context_data(self, **kwargs):
        context = super(PageDeviceView, self).get_context_data(**kwargs)

        if 'start' in self.request.GET:
            context['start'] = self.request.GET['start']

        if 'end' in self.request.GET:
            context['end'] = self.request.GET['end']

        context['device'] = self.object
        project = self.object.project
        context['project'] = project

        # Get all variables for this Sensor Graph
        sg = self.object.sg
        if sg and sg.variable_templates.count():
            logger.info(str(sg))
            variables = StreamVariable.objects.filter(project=project, lid__in=[v.lid for v in sg.variable_templates.all()])
            logger.info('Found {0} variables'.format(variables.count()))
            for var in variables:
                logger.info('Found var: {}'.format(var))

            context['streams'] = self.object.streamids.filter(device=self.object,
                                                              project=self.object.project,
                                                              block__isnull=True,
                                                              variable__in=variables,
                                                              variable__app_only=False,
                                                              variable__project__isnull=False)
        else:
            context['streams'] = self.object.streamids.filter(device=self.object,
                                                              project=self.object.project,
                                                              block__isnull=True,
                                                              variable__app_only=False,
                                                              variable__project__isnull=False)

        return context

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(PageDeviceView, self).dispatch(request, *args, **kwargs)





