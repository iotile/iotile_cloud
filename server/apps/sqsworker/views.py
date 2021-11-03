import logging
import json

from django.conf import settings
from django.views.generic import TemplateView, FormView
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.urls import reverse

from apps.staff.views import StaffRequiredMixin

from .workerhelper import str_to_class
from .stats import WorkerStats
from .forms import *
from .dynamodb import DynamoWorkerLogModel
from .tracker import WorkerUUID
from .common import ACTION_CLASS_MODULE
from .models import WorkerStatistics


class WorkerStatusView(StaffRequiredMixin, TemplateView):
    template_name = 'sqsworker/worker-status.html'

    def get_context_data(self, **kwargs):
        context = super(WorkerStatusView, self).get_context_data(**kwargs)
        context['stats'] = WorkerStats()

        return context


class ActionStatsView(StaffRequiredMixin, TemplateView):
    template_name = 'sqsworker/action-stats.html'

    def get_context_data(self, **kwargs):
        context = super(ActionStatsView, self).get_context_data(**kwargs)
        context['stats'] = WorkerStats()
        context['stats'].get_action_stats()

        return context


class WorkerDetailView(StaffRequiredMixin, TemplateView):
    template_name = 'sqsworker/worker-detail.html'

    def get_context_data(self, **kwargs):
        context = super(WorkerDetailView, self).get_context_data(**kwargs)
        context['uuid'] = kwargs['uuid']
        context['stats'] = WorkerStats()
        if getattr(settings, 'USE_DYNAMODB_WORKERLOG_DB'):
            try:
                context['tasks'] = DynamoWorkerLogModel.query(hash_key=context['uuid'], consistent_read=False)
            except Exception as e:
                context['error'] = str(e)

        return context


class WorkerScheduleView(StaffRequiredMixin, FormView):
    template_name = 'staff/form.html'
    success_url = '/staff/worker/'
    form_class = ScheduleWorkerForm

    def get_initial(self):
        initial = super(WorkerScheduleView, self).get_initial()
        if 'task' in self.request.GET and 'args' in self.request.GET and self.request.GET['task'] and self.request.GET['args']:
            initial['action'] = self.request.GET['task']
            initial['args']= self.request.GET['args'].replace("'", "\"")
        return initial

    def form_valid(self, form):
        try:
            args = json.loads(form.cleaned_data['args'])
        except Exception as e:
            messages.error(self.request, str(e))
            return HttpResponseRedirect(reverse('staff:worker:schedule'))
        action = form.cleaned_data['action']
        try:
            action_class = str_to_class(ACTION_CLASS_MODULE[action]['module'], ACTION_CLASS_MODULE[action]['class'])
            action_class.schedule(args=args)
            messages.info(self.request,"Task {} has been scheduled".format(action))
            return HttpResponseRedirect(reverse('staff:worker:home'))
        except Exception as e:
            messages.error(self.request, str(e))
            return HttpResponseRedirect(reverse('staff:worker:schedule'))

    def get_context_data(self, **kwargs):
        context = super(WorkerScheduleView, self).get_context_data(**kwargs)
        context['queue'] = getattr(settings, 'SQS_WORKER_QUEUE_NAME')
        return context

class WorkerCleanupAllView(StaffRequiredMixin, FormView):
    template_name = 'staff/form.html'
    success_url = '/staff/worker/'
    form_class = CleanupWorkerForm

    def form_valid(self, form):
        min_count = form.cleaned_data['min_count']
        WorkerUUID.cleanup(min_count=min_count)
        messages.info(self.request, 'Cached is now clean')
        return HttpResponseRedirect(reverse('staff:worker:home'))

    def get_context_data(self, **kwargs):
        context = super(WorkerCleanupAllView, self).get_context_data(**kwargs)
        context['title'] = "Clean all entries with count = 0"
        return context

class WorkerCleanupView(StaffRequiredMixin, FormView):
    template_name = 'staff/form.html'
    success_url = '/staff/worker/'
    form_class = CleanupWorkerForm

    def form_valid(self, form):
        WorkerUUID.cleanup_id(self.kwargs['uuid'])
        messages.info(self.request, 'Cache of worker {} is deleted'.format(self.kwargs['uuid']))
        return HttpResponseRedirect(reverse('staff:worker:home'))

    def get_context_data(self, **kwargs):
        context = super(WorkerCleanupView, self).get_context_data(**kwargs)
        context['title'] = "Clean cache of worker {}".format(self.kwargs['uuid'])
        return context


class WorkerActionDetailView(StaffRequiredMixin, TemplateView):
    template_name = 'sqsworker/action-detail.html'

    def get_context_data(self, **kwargs):
        context = super(WorkerActionDetailView, self).get_context_data(**kwargs)
        context['stats'] = WorkerStatistics.objects.filter(task_name=self.kwargs['action_name'])
        return context
