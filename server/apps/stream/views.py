import logging

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.utils.data_helpers.manager import DataManager
from apps.utils.gid.convert import gid2int, gid_split
from apps.utils.timezone_utils import str_utc
from apps.utils.views.basic import LoginRequiredAccessMixin

from .forms import *
from .mixins import StreamIdAccessMixin, StreamIdWriteAccessMixin, StreamVariableAccessMixin, StreamVariableWriteAccessMixin
from .models import *

logger = logging.getLogger(__name__)


class StreamVariableDetailView(StreamVariableAccessMixin, DetailView):
    model = StreamVariable

    def get_template_names(self):
        return 'stream/var-detail.html'

    def get_context_data(self, **kwargs):
        context = super(StreamVariableDetailView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        context['var'] = self.object
        return context


class StreamVariableCreateView(StreamVariableWriteAccessMixin, CreateView):
    model = StreamVariable
    form_class = StreamVariableForm

    def get_object(self, queryset=None):
        return None

    def get_template_names(self):
        if self.project:
            return 'project/form.html'
        return 'form.html'

    def get_success_url(self):
        if self.project:
            org = self.project.org
            return reverse('org:project:var-list', args=(org.slug, str(self.object.project.id),))
        else:
            return reverse('variable:detail', args=(self.object.slug,))

    def form_valid(self, form):
        assert(self.project)
        self.object = form.save(commit=False)
        self.object.lid = form.get_lid()
        self.object.created_by = self.request.user
        self.object.project = self.project
        self.object.org = self.project.org
        if self.object.input_unit:
            self.object.units = self.object.input_unit.unit_short
        elif self.object.output_unit:
            self.object.units = self.object.output_unit.unit_short
        if self.object.output_unit:
            self.object.decimal_places = self.object.output_unit.decimal_places
        self.object.save()
        StreamId.objects.create_after_new_variable(var=self.object)

        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        response = super(StreamVariableCreateView, self).form_invalid(form)
        return response

    def get_context_data(self, **kwargs):
        context = super(StreamVariableCreateView, self).get_context_data(**kwargs)
        context['title'] = _('Project Variable')
        return context

    def get_form_kwargs(self):
        kwargs = super(StreamVariableCreateView, self).get_form_kwargs()
        self.project = Project.objects.get_from_request(self.request)
        kwargs['project'] = self.project
        return kwargs


class StreamVariableUpdateView(StreamVariableWriteAccessMixin, UpdateView):
    model = StreamVariable
    form_class = StreamVariableForm

    def get_template_names(self):
        if self.project:
            return 'project/form.html'
        return 'form.html'

    def get_success_url(self):
        if self.project:
            org = self.project.org
            return reverse('org:project:var-list', args=(org.slug, str(self.project.id),))
        else:
            return reverse('variable:detail', args=(self.object.slug,))

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.lid = form.get_lid()
        if self.project:
            self.object.project = self.project
            self.object.org = self.project.org
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(StreamVariableUpdateView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        context['title'] = _('Project Variable')
        if self.project:
            context['org'] = self.project.org
            context['project'] = self.project
        return context

    def get_form_kwargs(self):
        kwargs = super(StreamVariableUpdateView, self).get_form_kwargs()
        vgid = self.object.slug
        vgid_elements = gid_split(vgid)
        pid = gid2int(vgid_elements[1])
        self.project = None
        if pid:
            self.project = Project.objects.get(gid=pid)
        kwargs['project'] = self.project
        return kwargs


class StreamVariableUnitsView(StreamVariableWriteAccessMixin, UpdateView):
    model = StreamVariable
    form_class = StreamVariableUnitsForm

    def get_template_names(self):
        if self.project:
            return 'project/form.html'
        return 'form.html'

    def get_success_url(self):
        if self.project:
            org = self.project.org
            return reverse('org:project:var-list', args=(org.slug, str(self.project.id),))
        else:
            return reverse('variable:detail', args=(self.object.slug,))

    def form_invalid(self, form):
        print(str(form.errors))
        return super(StreamVariableUnitsView, self).form_invalid(form)

    def form_valid(self, form):

        self.object = form.save(commit=False)
        if self.object.input_unit:
            self.object.units = self.object.input_unit.unit_short
        elif self.object.output_unit:
            self.object.units = self.object.output_unit.unit_short
        if self.object.output_unit:
            self.object.decimal_places = self.object.output_unit.decimal_places
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(StreamVariableUnitsView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        context['title'] = _('Project IO Configuration')
        if self.project:
            context['org'] = self.project.org
            context['project'] = self.project
        return context

    def get_form_kwargs(self):
        kwargs = super(StreamVariableUnitsView, self).get_form_kwargs()
        vgid = self.object.slug
        vgid_elements = gid_split(vgid)
        pid = gid2int(vgid_elements[1])
        self.project = None
        if pid:
            self.project = Project.objects.get(gid=pid)
        kwargs['project'] = self.project
        return kwargs


class StreamVariableDeleteView(StreamVariableWriteAccessMixin, DeleteView):
    model = StreamVariable
    project = None

    def get_queryset(self):
        return StreamVariable.objects.filter(created_by=self.request.user)

    def get_success_url(self):
        vgid = self.object.slug
        vgid_elements = gid_split(vgid)
        pid = gid2int(vgid_elements[1])
        project = None
        if pid:
            project = Project.objects.get(gid=pid)

        if project:
            org = project.org
            return reverse('org:project:var-list', args=(org.slug, str(project.id),))
        else:
            return reverse('home')

    def get_context_data(self, **kwargs):
        context = super(StreamVariableDeleteView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        kwargs['project'] = self.project
        context['back_url'] = self.request.META.get('HTTP_REFERER')
        return context


class StreamVariableListView(LoginRequiredAccessMixin, ListView):
    model = StreamVariable
    template_name = 'stream/var-list.html'

    def get_queryset(self):
        project = Project.objects.get_from_request(self.request)
        if project:
            org = Org.objects.get_from_request(self.request)
            if not org:
                return None
            return project.variables.all().order_by('name').select_related('var_type', 'input_unit', 'output_unit')
        else:
            return None

    def get_context_data(self, **kwargs):
        context = super(StreamVariableListView, self).get_context_data(**kwargs)
        org = Org.objects.get_from_request(self.request)
        if org:
            context['is_admin'] = org.is_admin(self.request.user)
        return context


class StreamIdDataTableView(StreamIdAccessMixin, DetailView):
    model = StreamId
    stream = None

    def get_template_names(self):
        return 'stream/streamid-data-table.html'

    def get_context_data(self, **kwargs):
        context = super(StreamIdDataTableView, self).get_context_data(**kwargs)
        context['stream'] = self.object
        context['production'] = settings.PRODUCTION

        return context


class StreamIdEventTableView(StreamIdAccessMixin, DetailView):
    model = StreamId
    stream = None

    def get_template_names(self):
        return 'stream/streamid-event-table.html'

    def get_context_data(self, **kwargs):
        context = super(StreamIdEventTableView, self).get_context_data(**kwargs)
        context['stream'] = self.object
        context['production'] = settings.PRODUCTION

        return context


class StreamIdMdoUpdateView(StreamIdWriteAccessMixin, UpdateView):
    model = StreamId
    template_name = 'project/form.html'

    def get_form_class(self):
        if self.object and self.object.data_type in ['E0', 'E1', 'E2', 'E3']:
            return StreamIdEventMdoForm
        return StreamIdDataMdoForm

    def get_success_url(self):
        assert(self.object.project)
        org = self.object.project.org
        return reverse('org:project:streamid-list', args=(org.slug, str(self.object.project.id),))

    def get_context_data(self, **kwargs):
        context = super(StreamIdMdoUpdateView, self).get_context_data(**kwargs)
        context['title'] = _('IO Configuration')
        context['stream'] = self.object
        return context


class StreamIdDisableUpdateView(StreamIdWriteAccessMixin, UpdateView):
    model = StreamId
    form_class = StreamIdDisableForm
    template_name = 'project/form.html'

    def get_success_url(self):
        assert(self.object.project)
        org = self.object.project.org
        return reverse('org:project:streamid-list', args=(org.slug, str(self.object.project.id),))

    def get_context_data(self, **kwargs):
        context = super(StreamIdDisableUpdateView, self).get_context_data(**kwargs)
        context['title'] = _('IO Configuration')
        return context


class UserStreamDataDeleteView(StreamIdWriteAccessMixin, UpdateView):
    model = StreamId
    form_class = StreamDataDeleteForm
    template_name = 'staff/form.html'

    def get_object(self, queryset=None):
        object = get_object_or_404(StreamId, slug=self.kwargs['slug'])
        if object.has_access(self.request.user):
            org = object.org
            if self.request.user.is_staff or org.is_admin(self.request.user):
                return object
        raise PermissionDenied("User is not allowed to delete stream data")

    def form_valid(self, form):
        assert self.object.project
        org = self.object.project.org
        base_url = reverse('org:project:stream:stream-data-delete-confirm', kwargs={'org_slug': org.slug,
                                                                                    'project_id': str(self.object.project.id),
                                                                                    'slug': self.object.slug})
        if 'delete_data' in self.request.POST:
            date_from_str = str_utc(form.cleaned_data['date_from']) if form.cleaned_data['date_from'] else ''
            date_to_str = str_utc(form.cleaned_data['date_to']) if form.cleaned_data['date_to'] else ''
            confirm_url = '{0}?from={1}&to={2}'.format(base_url, date_from_str, date_to_str)
        else:
            confirm_url = reverse('org:project:stream:stream-data-delete', kwargs={'org_slug': org.slug,
                                                                                   'project_id': str(self.object.project.id),
                                                                                   'slug': self.object.slug})
            messages.error(self.request, 'The delete request was sent improperly')
        return HttpResponseRedirect(confirm_url)

    def get_context_data(self, **kwargs):
        context = super(UserStreamDataDeleteView, self).get_context_data(**kwargs)
        context['title'] = _('Delete Stream Data')
        context['stream_slug'] = self.object.slug
        return context


class UserStreamDataDeleteConfirmView(StreamIdWriteAccessMixin, UpdateView):
    model = StreamId
    form_class = StreamDataDeleteConfirmForm
    template_name = 'stream/form_delete.html'

    def get(self, *arg, **kwargs):
        self.data_qs = self.get_stream_data_qs()
        self.event_qs = self.get_stream_event_data_qs()
        self.data_count = self.data_qs.count()
        self.event_count = self.event_qs.count()
        if self.data_count == 0 and self.event_count == 0:
            messages.error(self.request, 'No data points match the dates your provided')
            return HttpResponseRedirect(reverse('org:project:stream:stream-data-delete', kwargs=kwargs))
        return super(UserStreamDataDeleteConfirmView, self).get(*arg, **kwargs)

    def get_object(self, queryset=None):
        object = get_object_or_404(StreamId, slug=self.kwargs['slug'])
        if object.has_access(self.request.user):
            org = object.org
            if self.request.user.is_staff or org.is_admin(self.request.user):
                return object
        raise PermissionDenied("User is not allowed to delete stream data")

    def get_success_url(self):
        assert self.object.project
        org = self.object.project.org
        return reverse('org:project:device:detail', args=(org.slug, str(self.object.project.id), self.object.device.pk))

    def get_stream_data_qs(self):
        date_from_str = self.request.GET['from'] if self.request.GET['from'] else '1970-01-01T00:00:00Z'
        date_to_str = self.request.GET['to'] if self.request.GET['to'] else '2200-01-01T00:00:00Z'
        qs = DataManager.filter_qs('data', stream_slug=self.kwargs['slug'], timestamp__lte=date_to_str, timestamp__gte=date_from_str)
        return qs

    def get_stream_event_data_qs(self):
        date_from_str = self.request.GET['from'] if self.request.GET['from'] else '1970-01-01T00:00:00Z'
        date_to_str = self.request.GET['to'] if self.request.GET['to'] else '2200-01-01T00:00:00Z'
        qs = DataManager.filter_qs('event', stream_slug=self.kwargs['slug'], timestamp__lte=date_to_str, timestamp__gte=date_from_str)
        return qs

    def form_valid(self, form):
        org = self.object.org
        if org.is_admin(self.request.user):
            self.object = form.save(commit=False)
            # Delete StreamData
            data_qs = self.get_stream_data_qs()
            data_qs.delete()
            # Delete StreamData
            event_qs = self.get_stream_event_data_qs()
            event_qs.delete()
            if 'all' in self.request.GET:
                StreamId.objects.filter(slug=self.object.slug).delete()
            messages.success(self.request, 'Stream has been scheduled for delete')
        else:
            messages.error(self.request, 'User is not allowed to delete stream data')
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(UserStreamDataDeleteConfirmView, self).get_context_data(**kwargs)
        context['stream'] = self.object
        context['data_count'] = self.data_count
        context['event_count'] = self.event_count
        if 'from' in self.request.GET and self.request.GET['from']:
            context['from_parse'] = parse_datetime(self.request.GET['from'])
        else:
            context['from_parse'] = ''
        if 'to' in self.request.GET and self.request.GET['to']:
            context['to_parse'] = parse_datetime(self.request.GET['to'])
        else:
            context['to_parse'] = ''
        context['current_timezone'] = timezone.get_current_timezone_name()
        return context


class UserStreamDataDeleteAllConfirmView(StreamIdWriteAccessMixin, UpdateView):
    model = StreamId
    form_class = StreamDataDeleteAllForm
    template_name = 'stream/form_delete.html'

    def get_object(self, queryset=None):
        object = get_object_or_404(StreamId, slug=self.kwargs['slug'])
        if object.has_access(self.request.user):
            org = object.org
            if self.request.user.is_staff or org.is_admin(self.request.user):
                return object
        raise PermissionDenied("User is not allowed to delete stream data")

    def get_success_url(self):
        assert self.object.project
        org = self.object.project.org
        return reverse('org:project:device:detail', args=(org.slug, str(self.object.project.id), self.object.device.pk))

    def form_valid(self, form):
        org = self.object.org
        if org.is_admin(self.request.user):
            self.object = form.save(commit=False)
            self.object.delete_all_data()
            messages.success(self.request, 'Stream has been scheduled for delete')
        else:
            messages.error(self.request, 'User is not allowed to delete stream data')
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(UserStreamDataDeleteAllConfirmView, self).get_context_data(**kwargs)
        context['title'] = _('Delete all {0} stream data entries ?').format(self.object.get_data_count())
        return context
