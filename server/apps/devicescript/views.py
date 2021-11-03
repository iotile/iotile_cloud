import logging
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.views.generic import DetailView, CreateView, UpdateView, ListView, RedirectView
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from apps.s3file.views import S3FileUploadSuccessEndpointView, S3FileUploadView

from .models import *
from .forms import *

logger = logging.getLogger(__name__)


class DeviceScriptAccessMixin(object):

    def get_context_data(self, **kwargs):
        context = super(DeviceScriptAccessMixin, self).get_context_data(**kwargs)
        context['is_staff'] = self.request.user.is_staff
        context['org'] = self.org
        context.update(self.org.permissions(self.request.user))
        return context

    def get_object(self, queryset=None):

        script = get_object_or_404(DeviceScript, slug=self.kwargs['slug'])

        if script.org_id == self.org.id:
            if self.org.has_permission(self.request.user, 'can_manage_ota'):
                return script

        raise PermissionDenied("User has no access to this script")

    def get_queryset(self):
        return DeviceScript.objects.filter(org=self.org)

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.org = Org.objects.get_from_request(self.request)
        if self.org and not self.org.has_permission(self.request.user, 'can_manage_ota'):
            messages.error(self.request, 'User has no permissions to manage devices')
            return HttpResponseRedirect(self.org.get_absolute_url())
        return super(DeviceScriptAccessMixin, self).dispatch(request, *args, **kwargs)


class DeviceScriptListView(DeviceScriptAccessMixin, ListView):
    model = DeviceScript
    template_name = 'devicescript/list.html'


class DeviceScriptDetailView(DeviceScriptAccessMixin, DetailView):
    model = DeviceScript
    template_name = 'devicescript/detail.html'


class DeviceScriptCreateView(DeviceScriptAccessMixin, CreateView):
    model = DeviceScript
    form_class = DeviceScriptForm
    template_name = 'ota/form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.org = self.org
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(DeviceScriptCreateView, self).get_context_data(**kwargs)
        context['title'] = _('New Device Script')
        context['referer'] = self.request.META.get('HTTP_REFERER')
        return context


class DeviceScriptUpdateView(DeviceScriptAccessMixin, UpdateView):
    model = DeviceScript
    form_class = DeviceScriptForm
    template_name = 'ota/form.html'

    def form_valid(self, form):
        self.object = form.save()
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(DeviceScriptUpdateView, self).get_context_data(**kwargs)
        context['title'] = _('Update Device Script')
        context['referer'] = self.request.META.get('HTTP_REFERER')
        return context


class DeviceScriptReleaseView(DeviceScriptAccessMixin, UpdateView):
    model = DeviceScript
    form_class = DeviceScriptReleaseForm
    template_name = 'ota/form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        if self.object.released:
            self.object.released_on = timezone.now()
        else:
            self.object.released_on = None
        self.object.save()
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(DeviceScriptReleaseView, self).get_context_data(**kwargs)
        context['title'] = _('Device Script Release Form')
        context['referer'] = self.request.META.get('HTTP_REFERER')
        return context


class DeviceScriptS3FileUploadView(S3FileUploadView):

    def get_allowed_extensions(self):
        return ['trub']

    def get_fineuploader_storage_dirname(self):
        path = super(DeviceScriptS3FileUploadView, self).get_fineuploader_storage_dirname()
        return path + '/script'

    def get_fineuploader_success_endpoint(self):
        # return reverse('api-devicescript-success') + '?slug={}'.format(self.kwargs['slug'])
        org = Org.objects.get_from_request(self.request)
        return reverse('ota:script:upload-success', kwargs={'org_slug': org.slug, 'slug': self.kwargs['slug']})

    @method_decorator(login_required())
    def dispatch(self, *args, **kwargs):
        if not self.request.user.is_staff:
            raise PermissionDenied
        return super(DeviceScriptS3FileUploadView, self).dispatch(*args, **kwargs)


class DeviceScriptS3FileUploadSuccessEndpointView(S3FileUploadSuccessEndpointView):
    script = None

    def post_s3file_save(self, s3file):
        self.script = get_object_or_404(DeviceScript, slug=self.kwargs['slug'])
        self.script.file = s3file
        self.script.save()

    def get_response_data(self, s3file):
        if self.script:
            redirectURL = self.script.get_absolute_url()
        else:
            redirectURL = '/staff'

        response_data =  {
            'redirectURL': redirectURL
        }
        return response_data

