from django.conf import settings
from django.views.generic import TemplateView
from django.core.exceptions import PermissionDenied

from apps.utils.objects.view_mixins import ByTargetAccessMixin
from .models import DeviceLocation


class DeviceLocationView(ByTargetAccessMixin, TemplateView):
    template_name = 'devicelocation/map.html'

    def get_context_data(self, **kwargs):
        context = super(DeviceLocationView, self).get_context_data(**kwargs)
        context['api_key'] = getattr(settings, 'GOOGLE_API_KEY')
        target = self.get_target('can_read_device_locations')
        context['target'] = target
        context['project'] = target.project
        org = target.org
        context['org'] = org
        if org and not org.has_permission(self.request.user, 'can_access_classic'):
            raise PermissionDenied('User has no access to device locations')

        context['locations'] = DeviceLocation.objects.location_qs(user=self.request.user, target_slug=target.slug)
        return context
