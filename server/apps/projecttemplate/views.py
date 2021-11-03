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

from apps.org.models import Org
from apps.project.models import Project
from apps.stream.models import StreamVariable
from apps.stream.forms import StreamVariableForm

from .models import *
from .forms import *

logger = logging.getLogger(__name__)


class ProjectTemplateAccessMixin(object):

    def get_object(self, queryset=None):

        object = get_object_or_404(ProjectTemplate, slug=self.kwargs['slug'])
        if object.has_access(self.request.user):
            # Org owner always have access
            return object

        raise Http404

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(ProjectTemplateAccessMixin, self).dispatch(request, *args, **kwargs)


class ProjectTemplateEditAccessMixin(object):

    def get_project_object(self, queryset=None):

        slug = self.kwargs['template_slug']
        slug = slug.lower()
        object = get_object_or_404(ProjectTemplate, slug=slug)
        if object.has_write_access(self.request.user):
            # Org owner always have access
            return object

        raise Http404

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(ProjectTemplateEditAccessMixin, self).dispatch(request, *args, **kwargs)


class ProjectTemplateListView(ProjectTemplateAccessMixin, ListView):
    model = ProjectTemplate
    template_name = 'projecttemplate/list.html'

    def get_context_data(self, **kwargs):
        context = super(ProjectTemplateListView, self).get_context_data(**kwargs)
        context['project_list'] = self.object_list
        context['is_staff'] = self.request.user.is_staff
        return context


class ProjectTemplateDetailView(ProjectTemplateAccessMixin, DetailView):
    model = ProjectTemplate
    queryset = ProjectTemplate.objects.all()
    template_name = 'projecttemplate/detail.html'

    def get_context_data(self, **kwargs):
        context = super(ProjectTemplateDetailView, self).get_context_data(**kwargs)
        context['template'] = self.object
        context['is_owner'] = self.object.is_owner(self.request.user)
        return context


class ProjectTemplateCreateView(CreateView):
    model = ProjectTemplate
    form_class = ProjectTemplateForm
    template_name = 'form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(ProjectTemplateCreateView, self).get_context_data(**kwargs)
        context['title'] = _('New Project Template')
        return context

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(ProjectTemplateCreateView, self).dispatch(request, *args, **kwargs)

