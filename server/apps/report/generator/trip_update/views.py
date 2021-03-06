import json
import logging

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
from apps.report.models import UserReport
from apps.report.views import UserReportViewMixin
from apps.report.worker.report_generator import ReportGeneratorAction
from apps.utils.timezone_utils import str_utc
from apps.vartype.models import VarTypeOutputUnit

from ..base import ReportGenerator
from .forms import *

logger = logging.getLogger(__name__)


class TripUpdateReportConfigureView(UserReportViewMixin, UpdateView):
    model = UserReport
    form_class = TripUpdateConfigureForm
    template_name = "org/form.html"

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()
        return HttpResponseRedirect(reverse("org:report:list",
                                            kwargs={'org_slug': self.object.org.slug}))



class TripUpdateReportGenerateView(UserReportViewMixin, UpdateView):
    model = UserReport
    template_name = "org/form.html"
    form_class = TripUpdateReportGenerateForm

    def form_valid(self, form):
        self.object = form.save(commit=False)
        args = {
            'rpt': self.object.id,
            'start': None,
            'end': str_utc(timezone.now()),
            'attempt': 1
        }
        slug = form.cleaned_data['source']
        args['sources'] = [str(slug),]

        ReportGeneratorAction.schedule(args=args)
        messages.info(self.request,
                      'Task has been scheduled. You will receive the report via email shortly')

        return HttpResponseRedirect(reverse("org:report:list",
                                            kwargs={'org_slug': self.object.org.slug}))

    def get_form_kwargs(self):
        kwargs = super(TripUpdateReportGenerateView, self).get_form_kwargs()
        return kwargs
