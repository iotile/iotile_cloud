from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from apps.utils.views.basic import LoginRequiredAccessMixin
from apps.org.roles import NO_PERMISSIONS_ROLE
from apps.project.mixins import get_project_menu_extras

from .models import Device


class DeviceAccessMixin(LoginRequiredAccessMixin):

    def _check_url(self, device):
        if 'org_slug' in self.kwargs:
            if not device.org or device.org.slug != self.kwargs['org_slug']:
                raise PermissionDenied("URL is incorrectly formatted")
        if 'project_id' in self.kwargs:
            if not device.project or str(device.project.id) != self.kwargs['project_id']:
                raise PermissionDenied("URL is incorrectly formatted")

    def get_object(self, queryset=None):

        """Support both PK and Slug URLs"""
        if 'pk' in self.kwargs:
            device = get_object_or_404(Device, pk=self.kwargs['pk'])
        elif 'slug' in self.kwargs:
            device = get_object_or_404(Device, slug=self.kwargs['slug'])
        else:
            raise PermissionDenied('Bad URL')

        self._check_url(device)

        user = self.request.user
        if device.org.has_permission(user, 'can_access_classic'):
            return device

        raise PermissionDenied('User has no read permission to Device {}'.format(device.slug))

    def get_basic_context(self):
        context = {}
        org = self.object.org

        if self.object.project:
            context['project_menu_extras'] = get_project_menu_extras(self.object.project)

        if org:
            context.update(org.permissions(self.request.user))
        else:
            context.update(NO_PERMISSIONS_ROLE)

        return context



class DeviceWriteAccessMixin(DeviceAccessMixin):

    def get_object(self, queryset=None):

        device = get_object_or_404(Device, pk=self.kwargs['pk'])
        self._check_url(device)

        user = self.request.user
        if device.has_access(user) and device.org.has_permission(user, 'can_modify_device'):
            return device

        raise PermissionDenied('User has no permission to modify Device {}'.format(device.slug))


class DeviceCanResetAccessMixin(DeviceAccessMixin):

    def get_object(self, queryset=None):

        device = get_object_or_404(Device, pk=self.kwargs['pk'])
        self._check_url(device)

        user = self.request.user
        if device.org and device.org.has_permission(user, 'can_reset_device'):
            return device

        raise PermissionDenied('User has no permission to reset/move/trim data for device {}'.format(device.slug))


