import json
import logging
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.views.generic import CreateView, ListView, DeleteView, UpdateView
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied, ValidationError
from django.conf import settings
from django.urls import reverse
from django.contrib import messages
from django.utils import timezone

from apps.org.models import Org
from apps.vartype.models import VarTypeOutputUnit
from apps.utils.timezone_utils import str_utc

from apps.report.models import UserReport, GeneratedUserReport
from apps.report.worker.report_generator import ReportGeneratorAction
from apps.report.views import UserReportViewMixin
from apps.utils.aws.sqs import SqsPublisher

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
