import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DetailView, ListView, RedirectView, UpdateView
from django.views.generic.edit import FormView

from apps.s3images.views import (
    S3ImageDeleteView, S3ImageTitleUpdateView, S3ImageUploadSuccessEndpointView, S3ImageUploadView,
)
from apps.utils.views.basic import LoginRequiredAccessMixin

from .forms import *
from .models import *

logger = logging.getLogger(__name__)


class ComponentAccessMixin(LoginRequiredAccessMixin):

    def get_object(self, queryset=None):

        object = get_object_or_404(Component, pk=self.kwargs['pk'])
        if object.has_access(self.request.user):
            # Event owner always have access
            return object

        raise Http404


class ComponentListView(ComponentAccessMixin, ListView):
    model = Component
    template_name = 'component/list.html'

    def get_context_data(self, **kwargs):
        context = super(ComponentListView, self).get_context_data(**kwargs)
        context['is_staff'] = self.request.user.is_staff
        return context


class ComponentDetailView(ComponentAccessMixin, DetailView):
    model = Component
    template_name = 'component/detail.html'

    def get_context_data(self, **kwargs):
        context = super(ComponentDetailView, self).get_context_data(**kwargs)
        context['is_owner'] = self.object.is_owner(self.request.user)
        return context


class ComponentCreateView(LoginRequiredAccessMixin, CreateView):
    model = Component
    form_class = ComponentForm
    template_name = 'form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(ComponentCreateView, self).get_context_data(**kwargs)
        context['title'] = _('New Device Component')
        return context


class ComponentUpdateView(ComponentAccessMixin, UpdateView):
    model = Component
    form_class = ComponentForm
    template_name = 'form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(ComponentUpdateView, self).get_context_data(**kwargs)
        context['title'] = _('Update Device Component')
        return context


class ComponentS3ImageUploadView(S3ImageUploadView):
    fineuploader_item_limit = 5

    def get_fineuploader_success_endpoint(self):
        return reverse('component:upload-image-success', kwargs={'pk': self.kwargs['pk']})


class ComponentS3ImageUploadSuccessEndpointView(S3ImageUploadSuccessEndpointView):
    component = None

    def post_s3image_save(self, s3image):
        self.component = get_object_or_404(Component, pk=self.kwargs['pk'])
        self.component.images.add(s3image)

    def get_response_data(self, s3image):
        if self.component:
            redirectURL = self.component.get_absolute_url()
        else:
            redirectURL = s3image.get_absolute_url()

        response_data =  {
            'redirectURL': redirectURL
        }
        return response_data

class ComponentS3ImageDeleteView(S3ImageDeleteView):

    def get_success_url(self):
        component = get_object_or_404(Component, pk=self.kwargs['component_id'])
        return component.get_absolute_url()


class ComponentS3ImageTitleUpdateView(S3ImageTitleUpdateView):

    def get_success_url(self):
        component = get_object_or_404(Component, pk=self.kwargs['component_id'])
        return component.get_absolute_url()

