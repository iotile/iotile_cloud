from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from apps.utils.objects.utils import get_object_by_slug

class ByTargetAccessMixin(object):

    def get_target(self, permission='can_access_classic'):

        target_slug = self.kwargs['slug']

        n, target = get_object_by_slug(target_slug)
        user = self.request.user
        if not target or not target.has_access(user):
            raise PermissionDenied("User has no access")

        if not target.org.has_permission(user, permission):
            raise PermissionDenied("User has no access")

        return target

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(ByTargetAccessMixin, self).dispatch(request, *args, **kwargs)
