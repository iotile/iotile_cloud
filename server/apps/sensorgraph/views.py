import logging
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.views.generic import DetailView, CreateView, UpdateView, ListView
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from django.contrib import messages

from apps.org.models import Org
from apps.project.models import Project

from apps.s3file.views import S3FileUploadSuccessEndpointView, S3FileUploadView
from apps.utils.views.basic import LoginRequiredAccessMixin

from .models import *
from .forms import *

logger = logging.getLogger(__name__)


class SensorGraphAccessMixin(LoginRequiredAccessMixin):

    def get_object(self, queryset=None):

        object = get_object_or_404(SensorGraph, slug=self.kwargs['slug'])
        if object.has_access(self.request.user):
            # Org owner always have access
            return object

        raise Http404


class SensorGraphEditAccessMixin(object):

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_staff:
            raise PermissionDenied
        return super(SensorGraphEditAccessMixin, self).dispatch(request, *args, **kwargs)


class SensorGraphListView(SensorGraphAccessMixin, ListView):
    model = SensorGraph
    template_name = 'sensorgraph/list.html'

    def get_context_data(self, **kwargs):
        context = super(SensorGraphListView, self).get_context_data(**kwargs)
        context['sg_list'] = self.object_list
        context['is_staff'] = self.request.user.is_staff
        return context


class SensorGraphDetailView(SensorGraphAccessMixin, DetailView):
    model = SensorGraph
    queryset = SensorGraph.objects.all()
    template_name = 'sensorgraph/detail.html'

    def get_context_data(self, **kwargs):
        context = super(SensorGraphDetailView, self).get_context_data(**kwargs)
        context['sg'] = self.object
        context['is_owner'] = self.object.is_owner(self.request.user)
        context['is_staff'] = self.request.user.is_staff
        return context


class SensorGraphCreateView(LoginRequiredAccessMixin, CreateView):
    model = SensorGraph
    form_class = SensorGraphForm
    template_name = 'form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(SensorGraphCreateView, self).get_context_data(**kwargs)
        context['title'] = _('New Sensor Graph')
        return context


class SensorGraphUpdateView(LoginRequiredAccessMixin, UpdateView):
    model = SensorGraph
    form_class = SensorGraphForm
    template_name = 'form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(SensorGraphUpdateView, self).get_context_data(**kwargs)
        context['title'] = _('Update Sensor Graph')
        return context


class SensorGraphEditUiExtraView(LoginRequiredAccessMixin, UpdateView):
    model = SensorGraph
    template_name = 's3file/text-editor-form.html'
    form_class = SensorGraphUiExtraForm

    def form_valid(self, form):
        sg_slug = self.kwargs['slug']
        sg = get_object_or_404(SensorGraph, slug=sg_slug)
        sg.ui_extra = form.cleaned_data['extra']
        sg.save()
        return HttpResponseRedirect(sg.get_absolute_url())

    def form_invalid(self, form):
        errors = json.loads(form.errors.as_json())
        for error in errors['extra']:
            messages.error(message=error['message'], request=self.request)
        sg_slug = self.kwargs['slug']
        sg = get_object_or_404(SensorGraph, slug=sg_slug)
        return HttpResponseRedirect(sg.get_edit_ui_extra_url())

    def get_context_data(self, **kwargs):
        context = super(SensorGraphEditUiExtraView, self).get_context_data(**kwargs)
        context['title'] = _('Sensor Graph Json Editor')
        return context


class SensorGraphEditSgfView(LoginRequiredAccessMixin, UpdateView):
    model = SensorGraph
    template_name = 's3file/text-editor-form.html'
    form_class = SensorGraphSgfForm

    def form_valid(self, form):
        sg = form.save(commit=False)
        return HttpResponseRedirect(sg.get_absolute_url())

    def form_invalid(self, form):
        errors = json.loads(form.errors.as_json())
        for error in errors['sgf']:
            messages.error(message=error['message'], request=self.request)
        sg_slug = self.kwargs['slug']
        sg = get_object_or_404(SensorGraph, slug=sg_slug)
        return HttpResponseRedirect(sg.get_edit_sgf_url())

    def get_context_data(self, **kwargs):
        context = super(SensorGraphEditSgfView, self).get_context_data(**kwargs)
        context['title'] = _('SGF Editor')
        return context


class SensorGraphSGFUploadView(S3FileUploadView):

    def get_allowed_extensions(self):
        return ['sgf']

    def get_fineuploader_storage_dirname(self):
        path = super(SensorGraphSGFUploadView, self).get_fineuploader_storage_dirname()
        return path + '/sg'

    def get_fineuploader_success_endpoint(self):
        return reverse('sensor-graph:sgf-upload-success', kwargs={'slug': self.kwargs['slug']})

    @method_decorator(login_required())
    def dispatch(self, *args, **kwargs):
        if not self.request.user.is_staff:
            raise PermissionDenied
        return super(SensorGraphSGFUploadView, self).dispatch(*args, **kwargs)


class SensorGraphSGFUploadSuccessEndpointView(S3FileUploadSuccessEndpointView):
    sg = None

    def post_s3file_save(self, s3file):
        self.sg = get_object_or_404(SensorGraph, slug=self.kwargs['slug'])
        self.sg.sgf = s3file
        self.sg.save()

    def get_response_data(self, s3file):
        redirectURL = self.sg.get_absolute_url()

        response_data =  {
            'redirectURL': redirectURL
        }
        return response_data

