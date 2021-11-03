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


class DeviceFileAccessMixin(object):

    def get_context_data(self, **kwargs):
        context = super(DeviceFileAccessMixin, self).get_context_data(**kwargs)
        context['is_staff'] = self.request.user.is_staff
        context['vendor'] = 'arch-systems' # Hard code vendor name for now
        return context

    def get_object(self, queryset=None):

        if not self.request.user.is_staff:
            raise PermissionDenied("User has no access to this script")

        return get_object_or_404(DeviceFile, slug=self.kwargs['slug'])

    def get_queryset(self):
        return DeviceFile.objects.all()

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(DeviceFileAccessMixin, self).dispatch(request, *args, **kwargs)


class DeviceFileWriteAccessMixin(DeviceFileAccessMixin):

    def get_context_data(self, **kwargs):
        context = super(DeviceFileWriteAccessMixin, self).get_context_data(**kwargs)
        context['is_staff'] = self.request.user.is_staff
        context['org'] = self.released_by
        context.update(self.released_by.permissions(self.request.user))
        return context

    def get_object(self, queryset=None):
        file = super(DeviceFileWriteAccessMixin, self).get_object(queryset)

        if self.released_by.is_vendor and file.released_by_id == self.released_by.id:
            if self.released_by.has_permission(self.request.user, 'can_manage_ota'):
                return file

        raise PermissionDenied("User has no access to this device file")

    def get_queryset(self):
        return DeviceFile.objects.filter(released_by=self.released_by)

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.released_by = Org.objects.get_from_request(self.request)
        if self.released_by and not self.released_by.has_permission(self.request.user, 'can_manage_ota'):
            messages.error(self.request, 'User has no permissions to deploy device files')
            return HttpResponseRedirect(self.released_by.get_absolute_url())
        return super(DeviceFileWriteAccessMixin, self).dispatch(request, *args, **kwargs)


class DeviceFileListView(DeviceFileAccessMixin, ListView):
    model = DeviceFile
    template_name = 'devicefile/list.html'


class DeviceFileDetailView(DeviceFileAccessMixin, DetailView):
    model = DeviceFile
    template_name = 'devicefile/detail.html'


class DeviceFileCreateView(DeviceFileWriteAccessMixin, CreateView):
    model = DeviceFile
    form_class = DeviceFileForm
    template_name = 'form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.released_by = self.released_by
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(DeviceFileCreateView, self).get_context_data(**kwargs)
        context['title'] = _('New Device File')
        context['referer'] = self.request.META.get('HTTP_REFERER')
        return context


class DeviceFileUpdateView(DeviceFileAccessMixin, UpdateView):
    model = DeviceFile
    form_class = DeviceFileForm
    template_name = 'form.html'

    def get_object(self, queryset=None):
        device_file = super(DeviceFileUpdateView, self).get_object(queryset)

        if device_file.released_by.is_vendor:
            if device_file.released_by.has_permission(self.request.user, 'can_manage_ota'):
                return device_file

        raise PermissionDenied("User has no access to modify this device file")

    def form_valid(self, form):
        self.object = form.save()
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(DeviceFileUpdateView, self).get_context_data(**kwargs)
        context['title'] = _('Update Device File')
        context['referer'] = self.request.META.get('HTTP_REFERER')
        return context


class DeviceFileS3FileUploadView(S3FileUploadView):

    def get_allowed_extensions(self):
        return ['ship', 'trub']

    def get_fineuploader_storage_dirname(self):
        path = super(DeviceFileS3FileUploadView, self).get_fineuploader_storage_dirname()
        return path + '/device_file'

    def get_fineuploader_success_endpoint(self):
        return reverse('ota:file:upload-success', kwargs={'slug': self.kwargs['slug']})

    @method_decorator(login_required())
    def dispatch(self, *args, **kwargs):
        if not self.request.user.is_staff:
            raise PermissionDenied
        return super(DeviceFileS3FileUploadView, self).dispatch(*args, **kwargs)


class DeviceFileS3FileUploadSuccessEndpointView(S3FileUploadSuccessEndpointView):
    image = None

    def post_s3file_save(self, s3file):
        self.image = get_object_or_404(DeviceFile, slug=self.kwargs['slug'])
        self.image.file = s3file
        self.image.save()

    def get_response_data(self, s3file):
        if self.image:
            redirectURL = self.image.get_absolute_url()
        else:
            redirectURL = '/staff'

        response_data =  {
            'redirectURL': redirectURL
        }
        return response_data


