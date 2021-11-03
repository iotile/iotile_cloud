import logging
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.views.generic import DetailView, CreateView, UpdateView, ListView, TemplateView
from django.views.generic.edit import FormView
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils.translation import gettext_lazy as _

from apps.utils.views.basic import LoginRequiredAccessMixin

from .models import *
from .forms import *

logger = logging.getLogger(__name__)


class OrgTemplateAccessMixin(LoginRequiredAccessMixin):

    def get_object(self, queryset=None):

        object = get_object_or_404(OrgTemplate, slug=self.kwargs['slug'])
        if object.has_access(self.request.user):
            # Org owner always have access
            return object

        raise Http404


class OrgTemplateEditAccessMixin(LoginRequiredAccessMixin):

    def get_org_object(self, queryset=None):

        slug = self.kwargs['template_slug']
        slug = slug.lower()
        object = get_object_or_404(OrgTemplate, slug=slug)
        if object.has_write_access(self.request.user):
            # Org owner always have access
            return object

        raise Http404


class OrgTemplateListView(OrgTemplateAccessMixin, ListView):
    model = OrgTemplate
    template_name = 'orgtemplate/list.html'

    def get_context_data(self, **kwargs):
        context = super(OrgTemplateListView, self).get_context_data(**kwargs)
        context['org_list'] = self.object_list
        context['is_staff'] = self.request.user.is_staff
        return context


class OrgTemplateDetailView(OrgTemplateAccessMixin, DetailView):
    model = OrgTemplate
    queryset = OrgTemplate.objects.all()
    template_name = 'orgtemplate/detail.html'

    def get_context_data(self, **kwargs):
        context = super(OrgTemplateDetailView, self).get_context_data(**kwargs)
        context['template'] = self.object
        context['is_owner'] = self.object.is_owner(self.request.user)
        return context


class OrgTemplateCreateView(LoginRequiredAccessMixin, CreateView):
    model = OrgTemplate
    form_class = OrgTemplateForm
    template_name = 'form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(OrgTemplateCreateView, self).get_context_data(**kwargs)
        context['title'] = _('New Org Template')
        return context
