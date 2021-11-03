import json
import logging
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.views.generic import CreateView, ListView, DeleteView, UpdateView
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.contrib import messages
from django.utils import timezone

from apps.org.models import Org
from apps.vartype.models import VarTypeOutputUnit
from apps.utils.timezone_utils import str_utc

from apps.report.models import UserReport
from apps.report.worker.report_generator import ReportGeneratorAction
from apps.report.views import UserReportViewMixin

from .forms import *

logger = logging.getLogger(__name__)


class DefaultReportConfigureView(UserReportViewMixin, UpdateView):
    model = UserReport
    form_class = DefaultConfigureForm
    template_name = "org/form.html"

    def form_valid(self, form):
        self.object = form.save(commit=False)
        if 'project' in form.cleaned_data:
            project_slug = form.cleaned_data['project']
            self.object.sources.append(project_slug)
        self.object.save()
        return HttpResponseRedirect(reverse("org:report:list",
                                            kwargs={'org_slug': self.object.org.slug}))

    def form_invalid(self, form):
        logger.error(form.errors)
        return super(DefaultReportConfigureView, self).form_invalid(form)

    def get_form_kwargs(self):
        kwargs = super(DefaultReportConfigureView, self).get_form_kwargs()
        org = Org.objects.get_from_request(self.request)
        if self.object.config:
            kwargs['projects'] = org.projects.exclude(slug__in=self.object.sources)
        else:
            kwargs['projects'] = org.projects.all()
        return kwargs


class DefaultReportDefaultStep1View(UserReportViewMixin, UpdateView):
    model = UserReport
    template_name = "org/form.html"
    form_class = DefaultStep1Form

    def form_valid(self, form):
        self.object = form.save(commit=False)
        name = form.cleaned_data['name']
        type = form.cleaned_data['var_type']
        assert self.object.config and 'cols' in self.object.config

        self.object.config['cols'].append({
            'name': name,
            'type': type,
            'vars': []
        })
        self.object.save()
        index = len(self.object.config['cols']) - 1
        url = reverse("org:report:default:step2", kwargs={
            'org_slug': self.object.org.slug,
            'pk': self.object.id
        })
        url += '?column={}'.format(index)
        return HttpResponseRedirect(url)

    def get_form_kwargs(self):
        kwargs = super(DefaultReportDefaultStep1View, self).get_form_kwargs()
        org = Org.objects.get_from_request(self.request)
        kwargs['cols'] = self.object.config['cols']
        kwargs['var_type_choices'] = []
        if self.object.config:
            projects = org.projects.filter(slug__in=self.object.sources)
            for p in projects:
                variables = p.variables.all()
                for v in variables:
                    if not v.app_only:
                        if v.var_type.slug not in [vt[0] for vt in kwargs['var_type_choices']]:
                            kwargs['var_type_choices'].append((v.var_type.slug, v.var_type.name))
        return kwargs


class DefaultReportDefaultStep2View(UserReportViewMixin, UpdateView):
    model = UserReport
    template_name = "org/form.html"
    form_class = DefaultStep2Form

    def form_valid(self, form):
        self.object = form.save(commit=False)
        name = form.cleaned_data['name']
        variable_items = form.cleaned_data['variables']
        units = form.cleaned_data['units']
        aggregate_type = form.cleaned_data['aggregate_type']
        assert self.object.config and self.object.config['cols']
        col = None
        for col in self.object.config['cols']:
            if col['name'] == name:
                break
        if col:
            col['units'] = units
            col['aggregate'] = aggregate_type
            col['vars'] = [json.loads(item) for item in variable_items]
            self.object.save()
        return HttpResponseRedirect(reverse("org:report:list",
                                            kwargs={'org_slug': self.object.org.slug}))

    def get_form_kwargs(self):
        kwargs = super(DefaultReportDefaultStep2View, self).get_form_kwargs()
        if not self.object.config:
            return kwargs
        org = Org.objects.get_from_request(self.request)
        index = int(self.request.GET.get('column', 0))
        kwargs['variable_choices'] = []
        kwargs['unit_choices'] = []
        kwargs['name'] = 'ERROR'
        if 'cols' in self.object.config:
            col = self.object.config['cols'][index]
            kwargs['name'] = col['name']
            projects = org.projects.filter(slug__in=self.object.sources)
            var_type = col['type']
            unique_set = set()
            for p in projects:
                variables = p.variables.filter(var_type__slug=var_type)
                for v in variables:
                    if not v.app_only:
                        label = '{0} - {1}'.format(v.formatted_lid, v.name)
                        if v.formatted_lid not in unique_set:
                            item = {
                                "name": v.name,
                                "lid": v.formatted_lid
                            }
                            unique_set.add(v.formatted_lid)
                            kwargs['variable_choices'].append((json.dumps(item), label))
            # Get Units from the VarType
            if 'type' in col:
                units = VarTypeOutputUnit.objects.filter(var_type__slug=var_type)
                kwargs['unit_choices'] = [(u.slug, u.unit_full) for u in units]

        return kwargs


class DefaultReportGenerateView(UserReportViewMixin, UpdateView):
    model = UserReport
    template_name = "org/form.html"
    form_class = DefaultReportGenerateForm

    def form_valid(self, form):
        self.object = form.save(commit=False)
        args = {
            'rpt': self.object.id,
            'start': None,
            'end': str_utc(timezone.now()),
            'attempt': 1
        }
        start = form.cleaned_data['start']
        if start:
            args['start'] = str_utc(start)
        end = form.cleaned_data['end']
        if end:
            args['end'] = str_utc(end)

        ReportGeneratorAction.schedule(args=args)
        messages.info(self.request,
                      'Task has been scheduled. You will receive the report via email shortly')

        return HttpResponseRedirect(reverse("org:report:list",
                                            kwargs={'org_slug': self.object.org.slug}))

    def get_form_kwargs(self):
        kwargs = super(DefaultReportGenerateView, self).get_form_kwargs()
        org = Org.objects.get_from_request(self.request)
        return kwargs


