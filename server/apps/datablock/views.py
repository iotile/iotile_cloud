import json
import logging
import pprint
import re

from django.conf import settings
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, UpdateView, ListView, CreateView
from django.db import transaction
from django.contrib import messages

from rest_framework.reverse import reverse as api_reverse
from elasticsearch_dsl import Q

from apps.stream.models import StreamId
from apps.utils.views.basic import LoginRequiredAccessMixin
from apps.org.roles import NO_PERMISSIONS_ROLE
from apps.org.mixins import get_org_menu_extras
from apps.report.models import GeneratedUserReport
from apps.report.views import BaseGeneratedUserReportScheduleView
from apps.utils.data_mask.mask_utils import set_data_mask, clear_data_mask
from apps.utils.timezone_utils import str_utc
from apps.verticals.utils import get_data_block_vertical_helper

from .documents import DataBlockDocument
from .models import *
from .forms import *
from .tasks import schedule_archive, schedule_delete
from .data_utils import StreamDataCountHelper

logger = logging.getLogger(__name__)


class DataBlockAccessMixin(LoginRequiredAccessMixin):

    def get_basic_context(self):
        org = Org.objects.get_from_request(self.request)
        if org:
            return org.permissions(self.request.user)
        return NO_PERMISSIONS_ROLE

    def get_object(self, queryset=None):

        object = get_object_or_404(DataBlock, slug=self.kwargs['slug'])
        if object.has_access(self.request.user):
            return object

        raise PermissionDenied("User has no access to this Data Block")


class DataBlockWriteAccessMixin(DataBlockAccessMixin):

    def get_basic_context(self):
        if self.org:
            return self.org.permissions(self.request.user)
        return NO_PERMISSIONS_ROLE

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.org = Org.objects.get_from_request(self.request)
        if not self.org:
            messages.error(self.request, 'You are not a member or the Organization')
            return HttpResponseRedirect(reverse('home'))
        if not self.org or not self.org.has_permission(self.request.user, 'can_create_datablock'):
            messages.error(self.request, 'You are not allowed to create or modify this data blocks')
            return HttpResponseRedirect(self.org.get_absolute_url())
        return super(DataBlockWriteAccessMixin, self).dispatch(request, *args, **kwargs)


class DataBlockDetailView(DataBlockAccessMixin, DetailView):
    model = DataBlock
    template_name = 'datablock/detail.html'

    def get_context_data(self, **kwargs):
        context = super(DataBlockDetailView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        stream_dict = {}
        streams = self.object.streamids.filter(enabled=True)
        streams.select_related('variable')
        for s in streams:
            stream_dict[s.slug] = {'data_cnt': s.get_data_count(), 'event_cnt': s.get_event_count()}
        context['stream_dict'] = stream_dict

        context['generated_user_reports'] = GeneratedUserReport.objects.filter(
            source_ref=self.object.slug
        ).order_by('-created_on')

        context['data_counter'] = StreamDataCountHelper(self.object)

        return context


class DataBlockListView(DataBlockAccessMixin, ListView):
    model = DataBlock
    template_name = 'datablock/list.html'

    def get_queryset(self):
        return DataBlock.objects.none()

    def get_context_data(self, **kwargs):
        context = super(DataBlockListView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        org = Org.objects.get_from_request(self.request)
        device_slug = self.request.GET.get('device')

        if org:
            context['org'] = org
            context['api'] = api_reverse('datablock-datatable') + '?org={}'.format(org.slug)
            context['org_menu_extras'] = get_org_menu_extras(org)
            if device_slug:
                context['api'] += '&device={}'.format(device_slug)
        elif device_slug:
                context['api'] = api_reverse('datablock-datatable') + '?device={}'.format(device_slug)

        return context


class DataBlockCreateView(DataBlockWriteAccessMixin, CreateView):
    model = DataBlock
    form_class = DataBlockCreateForm
    template_name = 'org/form.html'

    def form_valid(self, form):
        device = get_object_or_404(Device, slug=self.kwargs['device_slug'])

        new_block_id = get_block_id(device)

        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.block = new_block_id
        self.object.device = device
        self.object.org = device.org
        self.object.save()

        # execute any application specific processing after
        # block is created
        helper = get_data_block_vertical_helper(self.object)
        on_complete = helper.on_complete(self.request.user)

        device.state = 'B0'
        device.save()

        done = schedule_archive(self.object, on_complete=on_complete)
        if done:

            messages.info(self.request,
                          'Task has been scheduled to create a device data archive for {}. You will receive an email when it is done.'.format(self.object.slug))

        return HttpResponseRedirect(self.object.org.get_archive_list_url())

    def form_invalid(self, form):
        print(form.errors)

    def get_context_data(self, **kwargs):
        context = super(DataBlockCreateView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        context['title'] = _('Create new Device Data Block (Archive)')
        context['back_url'] = self.request.META.get('HTTP_REFERER')
        return context


class DataBlockEditView(DataBlockWriteAccessMixin, UpdateView):
    model = DataBlock
    form_class = DataBlockBasicUpdateForm
    template_name = 'org/form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(DataBlockEditView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        context['title'] = _('Edit Device Data Block')
        return context


class DataBlockDeleteConfirmView(DataBlockWriteAccessMixin, UpdateView):
    model = DataBlock
    template_name = 'org/form.html'
    form_class = DataBlockDeleteConfirmForm

    def form_valid(self, form):
        self.object = form.save(commit=False)
        org = self.object.org

        retyped_slug = form.cleaned_data['retyped_slug']
        if self.object.slug != retyped_slug:
            messages.error(self.request, 'Block ID and retyped ID does not match')
            return HttpResponseRedirect(org.get_archive_list_url())

        pid = schedule_delete(block=self.object, user=self.request.user)
        if pid:
            messages.success(self.request, 'Data block has been scheduled for deletion ({}). You will receive an email when it is done.'.format(pid))

        return HttpResponseRedirect(org.get_archive_list_url())

    def get_context_data(self, **kwargs):
        context = super(DataBlockDeleteConfirmView, self).get_context_data(**kwargs)
        context['title'] = _('Are you sure you want to delete the archive with Block ID "{0}" and title "{1}"?'.format(
            self.object.slug, self.object.title
        ))
        return context

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.org = Org.objects.get_from_request(self.request)
        if not self.org:
            messages.error(self.request, 'You are not a member or the Organization')
            return HttpResponseRedirect(reverse('home'))
        if not self.org or not self.org.has_permission(self.request.user, 'can_delete_datablock'):
            messages.error(self.request, 'You are not allowed to delete this data blocks')
            return HttpResponseRedirect(self.org.get_absolute_url())
        return super(DataBlockDeleteConfirmView, self).dispatch(request, *args, **kwargs)


class DataBlockGeneratedUserReportScheduleView(BaseGeneratedUserReportScheduleView):
    template_name = "org/form.html"

    def get_source_ref_object(self):
        return get_object_or_404(DataBlock, slug=self.kwargs['slug'])


class DataBlockMaskView(DataBlockWriteAccessMixin, UpdateView):
    model = DataBlock
    form_class = DataBlockMaskForm
    template_name = 'org/utc_form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)

        start = form.cleaned_data.get('start', None)
        end = form.cleaned_data.get('end', None)
        if start or end:
            start_str = str_utc(start) if start else None
            end_str = str_utc(end) if end else None
            set_data_mask(self.object, start_str, end_str, [], [], user=self.request.user)
            messages.info(self.request, 'Block Mask Configuration Set {}'.format(self.object.slug))
        else:
            clear_data_mask(self.object, self.request.user)

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(DataBlockMaskView, self).get_context_data(**kwargs)
        context['title'] = _('Mask Block Data')
        return context

    def get_form_kwargs(self):
        kwargs = super(DataBlockMaskView, self).get_form_kwargs()
        kwargs['start'] = self.request.GET.get('start', None)
        kwargs['end'] = self.request.GET.get('end', None)
        return kwargs
