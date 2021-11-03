import json
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.views.generic import CreateView, ListView, DeleteView, UpdateView, DetailView
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.contrib import messages

from apps.org.models import Org
from apps.org.mixins import OrgWritePermissionViewMixin
from apps.utils.timezone_utils import str_utc

from .forms import *
from .models import *


class FleetViewMixin(object):
    org = None

    def get_context_data(self, **kwargs):
        context = super(FleetViewMixin, self).get_context_data(**kwargs)
        context['is_staff'] = self.request.user.is_staff
        context['org'] = self.org
        context.update(self.org.permissions(self.request.user))
        return context

    def get_object(self, queryset=None):
        fleet = get_object_or_404(Fleet, slug=self.kwargs['slug'])
        if fleet.org.has_permission(self.request.user, 'can_manage_ota'):
            return fleet

        raise PermissionDenied("User has no access to this Fleet")

    def get_queryset(self):
        if self.org and self.org.has_permission(self.request.user, 'can_manage_ota'):
            return Fleet.objects.filter(org=self.org)

        raise PermissionDenied("User has no access to this Fleet")

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.org = Org.objects.get_from_request(self.request)
        if self.org == None:
            return HttpResponseRedirect(reverse('home'))
        if not self.org.has_permission(self.request.user, 'can_manage_ota'):
            messages.error(self.request, 'User has no permissions to manage devices')
            return HttpResponseRedirect(self.org.get_absolute_url())

        return super(FleetViewMixin, self).dispatch(request, *args, **kwargs)


class FleetMembershipViewMixin(FleetViewMixin):

    def get_context_data(self, **kwargs):
        context = super(FleetMembershipViewMixin, self).get_context_data(**kwargs)
        context['is_staff'] = self.request.user.is_staff
        context['org'] = Org.objects.get_from_request(self.request)
        context.update(context['org'].permissions(self.request.user))
        return context

    def get_object(self, queryset=None):
        fleet_membership = get_object_or_404(FleetMembership, pk=self.kwargs['pk'])
        fleet = fleet_membership.fleet
        if fleet and fleet.org.has_permission(self.request.user, 'can_manage_ota'):
            return fleet_membership

        raise PermissionDenied("User has no access to this Fleet")

    def get_queryset(self):
        if self.org and self.org.has_permission(self.request.user, 'can_manage_ota'):
            return Fleet.objects.filter(org=self.org)

        raise PermissionDenied("User has no access to this Fleet")

    def get_success_url(self):
        fleet = get_object_or_404(Fleet, slug=self.kwargs['slug'])
        return fleet.get_absolute_url()


class FleetListView(FleetViewMixin, ListView):
    model = Fleet
    template_name = 'fleet/list.html'

    def get_context_data(self, **kwargs):
        context = super(FleetListView, self).get_context_data(**kwargs)
        org = Org.objects.get_from_request(self.request)
        if org:
            context['fleet_list'] = org.fleets.order_by('name')
        return context


class FleetCreateView(FleetViewMixin, CreateView):
    model = Fleet
    template_name = "ota/form.html"
    form_class = FleetForm

    def form_valid(self, form):
        org = Org.objects.get_from_request(self.request)
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.org = org
        self.object.save()
        return HttpResponseRedirect(self.object.get_absolute_url())

    def get_form_kwargs( self ):
        kwargs = super( FleetCreateView, self ).get_form_kwargs()
        kwargs['org_slug'] = self.kwargs['org_slug']
        return kwargs


class FleetUpdateView(FleetViewMixin, UpdateView):
    model = Fleet
    template_name = "ota/form.html"
    form_class = FleetForm

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()
        return HttpResponseRedirect(self.object.get_absolute_url())

    def get_form_kwargs( self ):
        kwargs = super( FleetUpdateView, self ).get_form_kwargs()
        kwargs['org_slug'] = self.kwargs['org_slug']
        return kwargs


class FleetDetailView(FleetViewMixin, DetailView):
    model = Fleet
    template_name = 'fleet/detail.html'

    def get_context_data(self, **kwargs):
        context = super(FleetDetailView, self).get_context_data(**kwargs)
        context['members'] = FleetMembership.objects.filter(fleet=self.object).select_related('device', 'device__project')
        context['always_on'] = context['members'].filter(always_on=True)
        context['access_point'] = context['members'].filter(is_access_point=True)
        return context


class FleetMemberAddView(FleetMembershipViewMixin, CreateView):
    model = FleetMembership
    form_class = FleetMembershipCreateForm
    template_name = 'ota/form.html'

    def get_success_url(self):
        return self.object.fleet.get_absolute_url()

    def form_valid(self, form):
        fleet = get_object_or_404(Fleet, slug=self.kwargs['slug'])

        self.object = form.save(commit=False)
        self.object.fleet = fleet
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(FleetMemberAddView, self).get_context_data(**kwargs)
        context['title'] = _('Add Device to Fleet')
        return context

    def get_form_kwargs( self ):
        kwargs = super( FleetMemberAddView, self ).get_form_kwargs()
        kwargs['fleet'] = get_object_or_404(Fleet, slug=self.kwargs['slug'])
        return kwargs


class FleetMemberEditView(FleetMembershipViewMixin, UpdateView):
    model = FleetMembership
    form_class = FleetMembershipUpdateForm
    template_name = 'ota/form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(FleetMemberEditView, self).get_context_data(**kwargs)
        context['title'] = _('Change Fleet Device Attributes')
        return context


class FleetMemberDeleteView(FleetMembershipViewMixin, DeleteView):
    model = FleetMembership

    def get_context_data(self, **kwargs):
        context = super(FleetMemberDeleteView, self).get_context_data(**kwargs)
        context['title'] = _('Remove device from Fleet')
        return context
