from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.contrib import messages

from apps.utils.views.basic import LoginRequiredAccessMixin
from apps.org.models import Org
from apps.project.models import Project

from .models import StreamVariable, StreamId


class StreamVariableAccessMixin(LoginRequiredAccessMixin):

    def get_object(self, queryset=None):

        var = get_object_or_404(StreamVariable, slug=self.kwargs['slug'])
        if var.org.has_multiple_permissions(self.request.user, ['can_access_classic', 'can_read_stream_data']):
            return var

        raise PermissionDenied("User has no access to this Stream Variable")

    def get_basic_context(self):
        org = self.object.org

        return {
            'is_admin': org.is_admin(self.request.user)
        }


class StreamVariableWriteAccessMixin(StreamVariableAccessMixin):

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        variable = self.get_object()
        if variable:
            self.project = variable.project
        else:
            self.project = Project.objects.get_from_request(self.request)

        if self.project:
            self.org = self.project.org
            if not self.org.has_multiple_permissions(self.request.user, ['can_access_classic', 'can_modify_device']):
                messages.error(self.request, 'You are not allowed to modify this variable')
                return HttpResponseRedirect(self.project.get_absolute_url())
        return super(StreamVariableWriteAccessMixin, self).dispatch(request, *args, **kwargs)


class StreamIdAccessMixin(LoginRequiredAccessMixin):

    def get_object(self, queryset=None):

        object = get_object_or_404(StreamId, slug=self.kwargs['slug'])
        if object.org.has_multiple_permissions(self.request.user, ['can_access_classic', 'can_read_stream_data']):
            return object

        raise PermissionDenied("User has no access to this Stream Id")


class StreamIdWriteAccessMixin(StreamIdAccessMixin):

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.org = Org.objects.get_from_request(self.request)
        if self.org and not self.org.has_multiple_permissions(self.request.user, ['can_access_classic', 'can_modify_device']):
            messages.error(self.request, 'You are not allowed to modify this stream')
            return HttpResponseRedirect(self.org.get_absolute_url())
        return super(StreamIdWriteAccessMixin, self).dispatch(request, *args, **kwargs)
