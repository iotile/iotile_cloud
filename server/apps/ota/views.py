import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DetailView, ListView, RedirectView, UpdateView
from django.views.generic.edit import FormView

from .forms import *
from .models import *

logger = logging.getLogger(__name__)


class OtaAccessMixin(object):

    def get_context_data(self, **kwargs):
        context = super(OtaAccessMixin, self).get_context_data(**kwargs)
        context['is_staff'] = self.request.user.is_staff
        context['org'] = self.org
        context.update(self.org.permissions(self.request.user))
        return context

    def get_object(self, queryset=None):

        deployment_request = get_object_or_404(DeploymentRequest, pk=self.kwargs['pk'])

        if deployment_request.org_id == self.org.id:
            if self.org.has_permission(self.request.user, 'can_manage_ota'):
                return deployment_request

        raise PermissionDenied("User has no access to this deployment request")

    def get_queryset(self):
        return DeploymentRequest.objects.filter(org=self.org)

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.org = Org.objects.get_from_request(self.request)
        if self.org and not self.org.has_permission(self.request.user, 'can_manage_ota'):
            messages.error(self.request, 'User has no permissions to manage devices')
            return HttpResponseRedirect(self.org.get_absolute_url())
        return super(OtaAccessMixin, self).dispatch(request, *args, **kwargs)


class OtaIndexView(OtaAccessMixin, ListView):
    model = DeploymentRequest
    template_name = 'ota/index.html'

    def get_context_data(self, **kwargs):
        context = super(OtaIndexView, self).get_context_data(**kwargs)
        context['fleets'] = Fleet.objects.filter(org=context['org'])
        context['scripts'] = DeviceScript.objects.filter(org=context['org'])
        context['requests'] = DeploymentRequest.objects.filter(org=context['org']).select_related('script', 'fleet')
        return context


class DeploymentRequestListView(OtaAccessMixin, ListView):
    model = DeploymentRequest
    template_name = 'ota/request_list.html'

    def get_queryset(self):
        qs = super(DeploymentRequestListView, self).get_queryset()
        return qs.select_related('script', 'fleet', 'org')


class DeploymentRequestDetailView(OtaAccessMixin, DetailView):
    model = DeploymentRequest
    template_name = 'ota/request_detail.html'


class DeploymentRequestCreateView(OtaAccessMixin, CreateView):
    model = DeviceScript
    form_class = DeploymentRequestForm
    template_name = 'ota/form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.org = self.org
        self.object.selection_criteria = form.cleaned_data['selection_criteria_text']
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(DeploymentRequestCreateView, self).get_context_data(**kwargs)
        context['title'] = _('New Deployment Request')
        context['referer'] = self.request.META.get('HTTP_REFERER')
        return context

    def get_form_kwargs( self ):
        kwargs = super( DeploymentRequestCreateView, self ).get_form_kwargs()
        kwargs['org'] = self.org
        return kwargs


class DeploymentRequestUpdateView(OtaAccessMixin, UpdateView):
    model = DeviceScript
    form_class = DeploymentRequestForm
    template_name = 'ota/form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.selection_criteria = form.cleaned_data['selection_criteria_text']
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(DeploymentRequestUpdateView, self).get_context_data(**kwargs)
        context['title'] = _('Edit Deployment Request')
        context['referer'] = self.request.META.get('HTTP_REFERER')
        return context

    def get_form_kwargs( self ):
        kwargs = super( DeploymentRequestUpdateView, self ).get_form_kwargs()
        kwargs['org'] = self.org
        return kwargs


class DeploymentRequestReleaseView(OtaAccessMixin, UpdateView):
    model = DeploymentRequest
    form_class = DeploymentRequestReleaseForm
    template_name = 'ota/form.html'

    def get_context_data(self, **kwargs):
        context = super(DeploymentRequestReleaseView, self).get_context_data(**kwargs)
        context['title'] = _('Deployment Request Publishing Form')
        context['referer'] = self.request.META.get('HTTP_REFERER')
        return context


class DeploymentRequestCompleteView(OtaAccessMixin, UpdateView):
    model = DeploymentRequest
    form_class = DeploymentRequestCompleteForm
    template_name = 'ota/form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.completed_on = timezone.now()
        self.object.save()
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(DeploymentRequestCompleteView, self).get_context_data(**kwargs)
        context['title'] = _('Deployment Request Complete Form')
        context['referer'] = self.request.META.get('HTTP_REFERER')
        return context


