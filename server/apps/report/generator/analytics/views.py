import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.org.models import Org
from apps.report.models import GeneratedUserReport, UserReport
from apps.report.views import UserReportViewMixin
from apps.report.worker.report_generator import ReportGeneratorAction
from apps.utils.aws.sqs import SqsPublisher
from apps.utils.timezone_utils import str_utc
from apps.vartype.models import VarTypeOutputUnit

from .forms import *

logger = logging.getLogger(__name__)


class AnalyticsReportConfigureView(UserReportViewMixin, UpdateView):
    model = UserReport
    form_class = AnalyticsConfigureForm
    template_name = "org/form.html"

    def form_valid(self, form):
        self.object = form.save(commit=False)
        form.set_config(self.object)
        self.object.save()
        return HttpResponseRedirect(reverse("org:report:list",
                                            kwargs={'org_slug': self.object.org.slug}))

    def form_invalid(self, form):
        logger.error(form.errors)
        return super(AnalyticsReportConfigureView, self).form_invalid(form)


class AnalyticsReportGenerateView(UserReportViewMixin, UpdateView):
    model = UserReport
    template_name = "org/form.html"
    form_class = AnalyticsReportGenerateForm

    def form_valid(self, form):
        self.object = form.save(commit=False)
        slug = form.cleaned_data['source']
        extra_args= form.cleaned_data['extra_args']
        template = self.object.config.get('template')

        if template:
            # Create GeneratedReport object
            gr = GeneratedUserReport.objects.create(
                created_by=self.request.user,
                report=self.object,
                label='{}: {}'.format(template, slug),
                org=self.object.org,
                source_ref=slug
            )

            report_worker_payload = {
                'report': str(gr.id),
                'template': template,
                'group_slug': str(slug),
                'user': self.request.user.email,
                'token': self.request.user.jwt_token,
                'args': extra_args
            }
            logger.info(report_worker_payload)

            sqs = SqsPublisher(getattr(settings, 'SQS_ANALYTICS_QUEUE_NAME'))
            sqs.publish(payload=report_worker_payload)

            messages.info(self.request,
                          'Task has been scheduled. You will receive the report via email shortly')
        else:
            messages.error(self.request, 'No template defined')

        return HttpResponseRedirect(reverse("org:report:list",
                                            kwargs={'org_slug': self.object.org.slug}))
