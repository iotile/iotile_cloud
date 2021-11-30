from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator

from apps.physicaldevice.mixins import DeviceAccessMixin
from apps.physicaldevice.models import Device
from apps.project.mixins import ProjectBaseAccessMixin
from apps.project.models import Project


class VerticalProjectAccessMixin(ProjectBaseAccessMixin):

    def get_object(self, queryset=None):

        object = get_object_or_404(Project, slug=self.kwargs['slug'])
        if object.has_access(self.request.user):
            return object

        raise PermissionDenied("User has no access to this Project")

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(VerticalProjectAccessMixin, self).dispatch(request, *args, **kwargs)


class VerticalDeviceAccessMixin(DeviceAccessMixin):

    pass
