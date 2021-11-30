import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView
from django.views.generic.edit import FormView

from apps.org.models import Org
from apps.project.models import Project
from apps.s3images.views import (
    S3ImageDeleteView, S3ImageTitleUpdateView, S3ImageUploadSuccessEndpointView, S3ImageUploadView,
)
from apps.utils.views.basic import LoginRequiredAccessMixin

from .forms import *
from .models import *

logger = logging.getLogger(__name__)


class ProductAccessMixin(LoginRequiredAccessMixin):

    def _has_access(self, obj, user):
        return obj.has_access(user)

    def get_object(self, queryset=None):

        slug = self.kwargs['template_slug'] if 'template_slug' in self.kwargs else self.kwargs['slug']
        object = get_object_or_404(DeviceTemplate, slug=slug)
        if self._has_access(object, self.request.user):
            # Org owner always have access
            return object

        raise Http404

    def get_queryset(self):
        if self.request.user.is_staff:
            return DeviceTemplate.objects.all().select_related('org')
        else:
            orgs = Org.objects.user_orgs_ids(self.request.user)
            return DeviceTemplate.objects.filter(org__in=orgs).select_related('org')

    def get_device_template_object(self, queryset=None):

        slug = self.kwargs['template_slug']
        slug = slug.lower()
        object = get_object_or_404(DeviceTemplate, slug=slug)
        if self._has_access(object, self.request.user):
            # Org owner always have access
            return object

        raise Http404


class ProductWriteAccessMixin(ProductAccessMixin):

    def _has_access(self, obj, user):
        return obj.has_write_access(user)


class ProductListView(ProductAccessMixin, ListView):
    model = DeviceTemplate
    template_name = 'devicetemplate/list.html'

    def get_queryset(self):
        return DeviceTemplate.objects.filter(active=True)

    def get_context_data(self, **kwargs):
        context = super(ProductListView, self).get_context_data(**kwargs)
        context['device_list'] = self.object_list
        context['is_staff'] = self.request.user.is_staff
        return context


class ProductDetailView(ProductAccessMixin, DetailView):
    model = DeviceTemplate
    queryset = DeviceTemplate.objects.all()
    template_name = 'devicetemplate/detail.html'

    def get_context_data(self, **kwargs):
        context = super(ProductDetailView, self).get_context_data(**kwargs)
        context['template'] = self.object
        context['is_owner'] = self.object.is_owner(self.request.user)
        context['is_staff'] = self.request.user.is_staff
        image = self.object.get_poster_image()
        if image:
            context['poster'] = image.medium_url
        return context


class ProductCreateView(ProductAccessMixin, CreateView):
    model = DeviceTemplate
    form_class = DeviceTemplateForm
    template_name = 'form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(ProductCreateView, self).get_context_data(**kwargs)
        context['title'] = _('New IOTile Product')
        return context


class ProductUpdateView(ProductWriteAccessMixin, UpdateView):
    model = DeviceTemplate
    form_class = DeviceTemplateForm
    template_name = 'form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(ProductUpdateView, self).get_context_data(**kwargs)
        context['title'] = _('Edit IOTile Product')
        return context


class AddComponentToProductView(ProductWriteAccessMixin, UpdateView):
    model = DeviceTemplate
    form_class = AddComponentToDeviceForm
    template_name = 'form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        component = form.get_component()
        slot_num = form.cleaned_data['slot_number']
        logger.info('Adding {0} to {1} as slot #{2}'.format(component, self.object, slot_num))
        DeviceSlot.objects.create(template=self.object, component=component, number=slot_num)
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(AddComponentToProductView, self).get_context_data(**kwargs)
        context['title'] = _('Add Component to Device Template')
        return context


class ProductS3ImageUploadView(S3ImageUploadView):
    fineuploader_item_limit = 5

    def get_fineuploader_success_endpoint(self):
        return reverse('template:upload-image-success', kwargs={'slug': self.kwargs['slug']})


class ProductS3ImageUploadSuccessEndpointView(S3ImageUploadSuccessEndpointView):
    device = None

    def post_s3image_save(self, s3image):
        self.device = get_object_or_404(DeviceTemplate, slug=self.kwargs['slug'])
        self.device.images.add(s3image)

    def get_response_data(self, s3image):
        if self.device:
            redirectURL = self.device.get_absolute_url()
        else:
            redirectURL = s3image.get_absolute_url()

        response_data =  {
            'redirectURL': redirectURL
        }
        return response_data


class ProductS3ImageDeleteView(ProductWriteAccessMixin, S3ImageDeleteView):

    def get_success_url(self):
        template = self.get_device_template_object()
        return template.get_absolute_url()


class ProductS3ImageTitleUpdateView(ProductWriteAccessMixin, S3ImageTitleUpdateView):

    def get_success_url(self):
        template = self.get_device_template_object()
        return template.get_absolute_url()
