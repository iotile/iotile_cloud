import logging
import datetime
import os
import json

from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView, RedirectView
from django.views.generic.edit import FormView, CreateView, DeleteView
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.staff.views import StaffRequiredMixin
from apps.staff.worker.staff_operations import StaffOperationsAction
from apps.project.models import Project
from apps.projecttemplate.models import ProjectTemplate
from apps.configattribute.models import ConfigAttribute, get_or_create_config_name
from apps.property.models import GenericProperty

from .forms import (
    NewStreamerForwarderConfigForm,
    ArchFxDeviceBatchForm,
    STREAMER_REPORT_FORWARDER_CONFIG_NAME
)

logger = logging.getLogger(__name__)
user_model = get_user_model()


class StaffStreamerReportForwarderListView(StaffRequiredMixin, TemplateView):
    template_name = 'staff/factory/forwarder-list.html'

    def get_context_data(self, **kwargs):
        """Find all ConfigAttributes for STREAMER_REPORT_FORWARDER_CONFIG_NAME"""
        context = super(StaffStreamerReportForwarderListView, self).get_context_data(**kwargs)

        name = get_or_create_config_name(STREAMER_REPORT_FORWARDER_CONFIG_NAME)
        context['configs'] = ConfigAttribute.objects.filter(name=name)
        return context


class StaffStreamerReportForwarderAddView(StaffRequiredMixin, CreateView):
    model = ConfigAttribute
    form_class = NewStreamerForwarderConfigForm
    template_name = 'staff/form.html'

    def get_success_url(self):
        return reverse('staff:streamer-report-forwarder')

    def form_valid(self, form):
        """
        Manually create new ConfigAttribute
            STREAMER_REPORT_FORWARDER_CONFIG_NAME
        for the given Org and adding the expected data with the API domain and key

        Args:
            form: NewStreamerForwarderConfigForm instance
        """
        self.object = form.save(commit=True)

        # Delete cache to ensure new config is respected
        # As we also cached the fact that there was no config for given Org
        cache.delete('{}::{}'.format(
            STREAMER_REPORT_FORWARDER_CONFIG_NAME,
            self.object.target[1:]
        ))

        msg = 'Added forwarder for {}'.format(self.object.target)
        messages.success(self.request, msg)
        return HttpResponseRedirect(self.get_success_url())

    def get_form_kwargs(self):
        """Pass User to form"""
        kwargs = super(StaffStreamerReportForwarderAddView, self).get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super(StaffStreamerReportForwarderAddView, self).get_context_data(**kwargs)
        context['title'] = _('Configure new Streamer Report Forwarder')
        return context


class StaffStreamerReportForwarderDeleteView(StaffRequiredMixin, DeleteView):
    model = ConfigAttribute
    template_name = 'staff/factory/forwarder-delete-confirm.html'

    def get_success_url(self):
        return reverse('staff:streamer-report-forwarder')

    def delete(self, *args, **kwargs):
        """Need to overwrite Delete function to also update cache"""
        self.object = self.get_object()
        cache.delete('{}::{}'.format(
            STREAMER_REPORT_FORWARDER_CONFIG_NAME,
            self.object.target[1:]
        ))
        return super(StaffStreamerReportForwarderDeleteView, self).delete(*args, **kwargs)

class StaffStreamerReportForwarderToggleView(StaffRequiredMixin, RedirectView):
    permanent = False
    query_string = False
    pattern_name = 'staff:streamer-report-forwarder'

    def get_redirect_url(self, *args, **kwargs):
        """Just toggle the enabled field, delete cache and return"""
        config = get_object_or_404(ConfigAttribute, pk=kwargs['pk'])
        config.data['enabled'] = not config.data.get('enabled', False)
        config.save()
        # Delete cache to ensure change is respected
        cache.delete('{}::{}'.format(
            STREAMER_REPORT_FORWARDER_CONFIG_NAME,
            config.target[1:]
        ))
        return reverse('staff:streamer-report-forwarder')


class ArchFXCreateDeviceBatchView(StaffRequiredMixin, FormView):
    template_name = 'staff/form.html'
    form_class = ArchFxDeviceBatchForm
    success_url = '/staff/factory/'

    def form_valid(self, form):
        operation_args = {
            'template': form.cleaned_data['template'].slug,
            'sg': form.cleaned_data['sg'].slug,
            'org': form.cleaned_data['org'].slug,
            'name_format': form.cleaned_data['name_format'],
            'num_devices': form.cleaned_data['num_devices']
        }
        msg = 'Successfully scheduled task to create  {0} \'{1}\' devices with SG {2}'.format(
            form.cleaned_data['num_devices'], form.cleaned_data['template'], form.cleaned_data['sg']
        )

        payload = {
            'operation': 'create_devices',
            'user': self.request.user.slug,
            'args': operation_args
        }
        StaffOperationsAction.schedule(payload)

        messages.success(self.request, msg)
        return super(ArchFXCreateDeviceBatchView, self).form_valid(form)
