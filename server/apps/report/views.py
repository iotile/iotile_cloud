import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, DetailView, ListView, RedirectView, UpdateView

from apps.org.models import Org
from apps.utils.objects.utils import get_object_by_slug
from apps.utils.timezone_utils import str_utc
from apps.utils.views.basic import LoginRequiredAccessMixin

from .forms import *
from .models import UserReport

logger = logging.getLogger(__name__)


class UserReportViewMixin(LoginRequiredAccessMixin):

    def get_object(self, queryset=None):
        object = get_object_or_404(UserReport, pk=self.kwargs['pk'])
        if object.has_access(self.request.user):
            return object

        raise PermissionDenied("User has no access to this Report")

    def get_queryset(self):
        org = Org.objects.get_from_request(self.request)
        return UserReport.objects.filter(org=org, active=True)


class UserReportListView(UserReportViewMixin, ListView):
    model = UserReport
    template_name = 'report/list.html'


class UserReportCreateView(UserReportViewMixin, CreateView):
    model = UserReport
    template_name = "org/form.html"
    form_class = UserReportCreateForm

    def form_valid(self, form):
        org = Org.objects.get_from_request(self.request)
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.org = org
        self.object.save()
        return HttpResponseRedirect(reverse("org:report:list", kwargs={'org_slug': org.slug}))


class UserReportAddRecipientView(UserReportViewMixin, UpdateView):
    model = UserReport
    template_name = "org/form.html"
    form_class = UserReportAddRecipientForm

    def form_valid(self, form):
        self.object = form.save(commit=False)
        recipients = form.cleaned_data['recipients']
        self.object.notification_recipients = recipients
        extras = form.cleaned_data['extras']
        extra_emails = extras.split('\n')
        for extra_email in extra_emails:
            extra_email = extra_email.strip()
            if extra_email:
                self.object.notification_recipients.append('email:{}'.format(extra_email))
        self.object.save()
        return HttpResponseRedirect(reverse("org:report:list",
                                            kwargs={'org_slug': self.object.org.slug}))

    def get_form_kwargs(self):
        kwargs = super(UserReportAddRecipientView, self).get_form_kwargs()
        org = Org.objects.get_from_request(self.request)
        kwargs['org'] = org
        return kwargs


class UserReportDeleteView(UserReportViewMixin, DeleteView):
    model = UserReport
    project = None

    def get_success_url(self):
        org = Org.objects.get_from_request(self.request)
        return reverse('org:report:list', args=(org.slug,))


class GeneratedUserReportDetailView(LoginRequiredAccessMixin, DetailView):
    model = GeneratedUserReport
    template_name = "report/generated-detail.html"

    def get_object(self, queryset=None):
        object = get_object_or_404(GeneratedUserReport, pk=self.kwargs['pk'])
        if object.has_access(self.request.user):
            return object

        raise PermissionDenied("User has no access to this Report")

    def get_context_data(self, **kwargs):
        context = super(GeneratedUserReportDetailView, self).get_context_data(**kwargs)
        org = self.object.org
        context['can_write_reports'] = org and not org.has_permission(self.request.user, 'can_write_reports')
        return context


class GeneratedUserReportEditView(LoginRequiredAccessMixin, UpdateView):
    model = GeneratedUserReport
    template_name = "org/form.html"
    form_class = GeneratedUserReportEditForm

    def get_object(self, queryset=None):
        object = get_object_or_404(GeneratedUserReport, pk=self.kwargs['pk'])
        if object.has_access(self.request.user):
            return object

        raise PermissionDenied("User has no access to this Report")

    def form_valid(self, form):
        self.object = form.save()
        return HttpResponseRedirect(self.object.get_absolute_url())


class GeneratedUserReportDeleteView(LoginRequiredAccessMixin, DeleteView):
    model = GeneratedUserReport
    project = None

    def get_object(self, queryset=None):
        object = get_object_or_404(GeneratedUserReport, pk=self.kwargs['pk'])
        if object.has_access(self.request.user):
            return object

        raise PermissionDenied("User has no access to this Report")

    def get_success_url(self):
        name, ref = get_object_by_slug(str(self.object.source_ref))
        return ref.get_absolute_url()


class GeneratedUserReportPublicRedirect(RedirectView):

    def get_redirect_url(self, *args, **kwargs):
        rpt = get_object_or_404(GeneratedUserReport, pk=kwargs['pk'])
        if rpt.public:
            if rpt.index_file:
                return rpt.get_link()
            else:
                messages.info(self.request, 'Public link is not ready')
                org = rpt.org
                if org and org.has_permission(self.request.user, 'can_access_reports'):
                    return rpt.get_absolute_url()
                return reverse('home')
        messages.error(self.request, 'Report not found')
        return reverse('home')


class BaseGeneratedUserReportScheduleView(CreateView):
    model = GeneratedUserReport
    template_name = "org/form.html"
    form_class = GeneratedUserReportForm

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.source_ref = self.ref.slug
        self.object.org = self.ref.org
        self.object.save()
        form.schedule_analysis(self.object)
        return HttpResponseRedirect(self.ref.get_absolute_url())

    def get_form_kwargs(self):
        kwargs = super(BaseGeneratedUserReportScheduleView, self).get_form_kwargs()
        kwargs['ref'] = self.ref
        return kwargs

    def get_source_ref_object(self):
        return None

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.ref = self.get_source_ref_object()
        org = self.ref.org
        if org and not org.has_permission(self.request.user, 'can_create_reports'):
            messages.error(self.request, 'You are not allowed to create reports')
            return HttpResponseRedirect(self.ref.get_absolute_url())
        return super(BaseGeneratedUserReportScheduleView, self).dispatch(request, *args, **kwargs)
