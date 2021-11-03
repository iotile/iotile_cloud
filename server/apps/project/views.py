import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView
from django.views.generic.edit import FormView

from apps.org.models import Org
from apps.physicaldevice.models import Device
from apps.stream.models import StreamId, StreamVariable
from apps.streamfilter.models import State, StreamFilter
from apps.streamnote.models import StreamNote
from apps.utils.data_helpers.manager import DataManager
from apps.utils.views.basic import LoginRequiredAccessMixin
from apps.verticals.utils import ProjectDetailViewHelper

from .forms import *
from .mixins import ProjectBaseAccessMixin
from .models import *
from .utils import clone_project, create_project_from_template
from .worker.delete_project import ProjectDeleteAction

logger = logging.getLogger(__name__)


class ProjectAccessMixin(ProjectBaseAccessMixin):

    def get_object(self, queryset=None):
        return self.get_project()


class ProjectWriteAccessMixin(ProjectAccessMixin):

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.org = Org.objects.get_from_request(self.request)
        if not self.org.has_write_access(self.request.user):
            messages.error(self.request, 'You are not allowed to modify this project')
            return HttpResponseRedirect(self.org.get_absolute_url())
        return super(ProjectWriteAccessMixin, self).dispatch(request, *args, **kwargs)


class ProjectDetailView(ProjectAccessMixin, DetailView):
    model = Project

    def get_template_names(self):
        # Check if there is an application specific Project View
        template = ProjectDetailViewHelper.get_template_names(self.object)
        if template is not None:
            return template

        return 'project/detail.html'

    def get_context_data(self, **kwargs):
        context = super(ProjectDetailView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context(self.object))

        # Check if there is an application specific Project Context
        app_context = ProjectDetailViewHelper.get_vertical_context_data(self.object)
        if app_context is not None:
            context.update(app_context)
        else:
            context['devices'] = self.object.devices.all()
            context['streams'] = self.object.streamids.all()
            context['variables'] = self.object.variables.all()

        context['api_key'] = getattr(settings, 'GOOGLE_API_KEY')
        context['is_staff'] = self.request.user.is_staff
        context['filters'] = StreamFilter.objects.filter(project=self.object)
        context['webapp'] = self.object.get_webapp_url()

        return context


class ProjectCreateView(LoginRequiredAccessMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = 'form.html'

    def form_valid(self, form):
        org = Org.objects.get_from_request(self.request)
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.org = org
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(ProjectCreateView, self).get_context_data(**kwargs)
        context['title'] = _('New Project')
        return context


class ProjectUpdateView(ProjectWriteAccessMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = 'project/update-form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(ProjectUpdateView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context(self.object))
        context['title'] = _('Update Project')
        context['devices'] = Device.objects.filter(project=self.object.id)
        return context


class ProjectDeleteView(ProjectWriteAccessMixin, FormView):
    model = Project
    template_name = 'project/delete.html'
    form_class = DeleteProjectForm

    def get_success_url(self):
        return reverse('org:detail', kwargs={'slug': str(self.org.slug)})

    def form_valid(self, form):
        self.object = form.save(commit=False)
        project_name = form.cleaned_data['project_name']
        project = self.get_object()
        if project.name != project_name:
            messages.error(self.request, 'Project name and retyped name does not match')
            return HttpResponseRedirect(reverse('org:detail', kwargs={'slug': str(self.org.slug)}))

        args = {
            'user': self.request.user.slug,
            'project_slug': project.slug,
        }
        ProjectDeleteAction.schedule(args=args)
        messages.info(
            self.request,
            'Task has been scheduled to delete project {}. You will receive an email when it is done.'.format(
                project.slug,
            ),
        )

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(ProjectDeleteView, self).get_context_data(**kwargs)
        project = self.get_object()
        context.update(self.get_basic_context(project))
        context['title'] = _('Delete Project')
        context['project'] = get_object_or_404(Project, pk=project.id)
        context['streams'] = StreamId.objects.filter(project=project).count()
        context['data_streams'] = DataManager.filter_qs('data', project_slug=project.slug).count()
        context['variables'] = StreamVariable.objects.filter(project=project).count()
        context['stream_events'] = DataManager.filter_qs('event', project_slug=project.slug).count()
        context['stream_notes'] = StreamNote.objects.filter(target_slug=project.slug).count()

        return context


class DashboardStreamIdListView(ProjectAccessMixin, DetailView):
    model = Project
    template_name = 'stream/streamid-list.html'

    def get_context_data(self, **kwargs):
        context = super(DashboardStreamIdListView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context(self.object))
        cond1 = Q(block__isnull=True, device__isnull=False, device__active=True)
        cond2 = Q(block__isnull=True, device__isnull=True)
        context['streams'] = self.object.streamids.filter(cond1 | cond2).select_related(
            'variable', 'device'
        )
        return context


class ProjectCloneView(ProjectWriteAccessMixin, UpdateView):
    template_name = 'project/form.html'
    model = Project
    form_class = ProjectCloneForm

    def form_valid(self, form):
        self.object = form.save(commit=False)
        new_name = form.cleaned_data['new_name']
        new_org = form.cleaned_data['new_org']

        project_dst, msg = clone_project(
            src_project=self.object,
            dst_project_name=new_name,
            description='',
            dst_org=new_org,
            dst_owner=self.request.user
        )

        logger.info(msg)
        messages.success(self.request, msg)

        return HttpResponseRedirect(project_dst.get_absolute_url())

    def get_context_data(self, **kwargs):
        context = super(ProjectCloneView, self).get_context_data(**kwargs)
        context['title'] = _('Clone this Project')
        context.update(self.get_basic_context(self.object))
        return context

    def get_form_kwargs(self):
        kwargs = super(ProjectCloneView, self).get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class ProjectCreateFromTemplateView(LoginRequiredAccessMixin, FormView):
    template_name = 'org/form.html'
    form_class = ProjectCreateFromTemplateForm

    def form_valid(self, form):
        name = form.cleaned_data['new_name']
        project_template = ProjectTemplate.objects.filter(name='Default Template').last()
        about = form.cleaned_data['about']
        org = Org.objects.get_from_request(self.request)

        project, msg = create_project_from_template(
            created_by=self.request.user,
            project_name=name,
            description=about,
            org=org,
            project_template=project_template
        )

        logger.info(msg)
        messages.success(self.request, msg)

        return HttpResponseRedirect(project.get_absolute_url())

    def get_context_data(self, **kwargs):
        context = super(ProjectCreateFromTemplateView, self).get_context_data(**kwargs)
        context['title'] = _('New Project Setup')
        return context

    def get_form_kwargs(self):
        kwargs = super(ProjectCreateFromTemplateView, self).get_form_kwargs()
        kwargs['org_slug'] = self.kwargs['org_slug']
        return kwargs


class ProjectStreamFilterCreateView(ProjectWriteAccessMixin, CreateView):
    model = StreamFilter
    form_class = ProjectStreamFilterForm
    template_name = 'project/form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.project = self.project
        self.object.created_by = self.request.user
        self.object.save()
        for state in form.cleaned_data['states']:
            State.objects.create(label=state, filter=self.object, created_by=self.request.user)
        self.kwargs['slug'] = self.object.slug
        return HttpResponseRedirect(reverse("filter:detail", kwargs={'slug': self.object.slug}))

    def get_context_data(self, **kwargs):
        context = super(ProjectStreamFilterCreateView, self).get_context_data(**kwargs)
        context['title'] = _('New Stream Filter for project {}'.format(self.project))
        context.update(self.get_basic_context(self.object))
        return context

    def get_form_kwargs(self):
        kwargs = super(ProjectStreamFilterCreateView, self).get_form_kwargs()
        self.project = Project.objects.get(pk=self.kwargs['pk'])
        kwargs['project'] = self.project
        return kwargs


class ProjectPropertyView(ProjectAccessMixin, DetailView):
    model = Project
    template_name = 'project/property-detail.html'

    def get_context_data(self, **kwargs):
        context = super(ProjectPropertyView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context(self.object))
        context['properties'] = self.object.get_properties_qs()
        self.kwargs['target_slug'] = self.object.slug
        return context
