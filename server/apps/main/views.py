
import logging
from django.template import RequestContext
from django.views.generic.edit import FormView
from django.http import HttpResponseRedirect
from django.views.generic import DetailView, TemplateView, CreateView
from django.urls import reverse
from django.contrib import admin
from django.conf import settings
from django.views.generic import View
from django.contrib import messages
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic.base import RedirectView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from django.contrib.auth import get_user_model
from django.urls import reverse_lazy

from apps.org.models import Org, OrgMembership
from apps.project.models import Project
from apps.project.forms import ProjectCreateFromTemplateForm
from .forms import *

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL', 'auth.User')

# Get an instance of a logger
logger = logging.getLogger(__name__)
user_model = get_user_model()


class HomeIndexView(TemplateView):
    orgs = None

    def get_template_names(self):
        user = self.request.user

        if user.is_authenticated:
            template_name = 'main/index.html'
        else:
            template_name = 'main/landing.html'

        return template_name

    def get_context_data(self, **kwargs):
        context = super(HomeIndexView, self).get_context_data(**kwargs)

        context['production'] = settings.PRODUCTION
        context['recaptcha_public_key'] = settings.RECAPTCHA_PUBLIC_KEY
        context['user'] = self.request.user
        context['user_count'] = user_model.objects.count()
        if self.request.user.is_authenticated:
            context['orgs'] = Org.objects.user_orgs_qs(self.request.user).order_by('name').prefetch_related(
                'devices', 'projects', 'membership')

        return context

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseRedirect('/account/login')
        self.orgs = Org.objects.user_orgs_qs(request.user)
        if not self.orgs.exists():
            return HttpResponseRedirect(reverse('onboard-step-org'))
        return super(HomeIndexView, self).dispatch(request, *args, **kwargs)


class OnBoardOrgStepView(CreateView):
    model = Org
    form_class = OnboardOrgForm
    template_name = 'onboard/onboard-form.html'
    success_url = reverse_lazy('onboard-step-device')

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.save()
        self.object.register_user(user=self.request.user, is_admin=True, role='a0')

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):

        context = super(OnBoardOrgStepView, self).get_context_data(**kwargs)
        context['note'] = None
        context['title'] = _('Step 1. Enter Company name')
        context['step'] = 1
        context['orgs'] = self.orgs.order_by('name')
        context['welcome'] = True
        return context

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.orgs = Org.objects.user_orgs_qs(request.user)
        if self.orgs.exists():
            return HttpResponseRedirect(reverse('onboard-step-org-done'))
        return super(OnBoardOrgStepView, self).dispatch(request, *args, **kwargs)

class OnBoardOrgDoneStepView(TemplateView):
    orgs = None
    template_name = 'onboard/onboard-step-org-done.html'

    def get_context_data(self, **kwargs):
        context = super(OnBoardOrgDoneStepView, self).get_context_data(**kwargs)

        context['step'] = 1
        context['title'] = _('Step 1. Enter Company name')
        context['user'] = self.request.user
        context['next'] = reverse_lazy('onboard-step-device')
        context['orgs'] = self.orgs.order_by('name')
        context['welcome'] = True

        return context

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.orgs = Org.objects.user_orgs_qs(request.user)
        return super(OnBoardOrgDoneStepView, self).dispatch(request, *args, **kwargs)


class OnBoardDeviceStepView(TemplateView):
    orgs = None
    template_name = 'onboard/onboard-step-device.html'

    def get_context_data(self, **kwargs):
        context = super(OnBoardDeviceStepView, self).get_context_data(**kwargs)

        context['step'] = 2
        context['title'] = _('Step 2. Set Up Device')
        context['user'] = self.request.user
        context['orgs'] = self.orgs
        context['next'] = reverse_lazy('onboard-step-mobile')
        context['welcome'] = False

        return context

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.orgs = Org.objects.user_orgs_qs(request.user)
        if not self.orgs.exists():
            msg = 'You need to setup your company first'
            messages.success(self.request, msg)
            return HttpResponseRedirect(reverse('onboard-step-org'))

        return super(OnBoardDeviceStepView, self).dispatch(request, *args, **kwargs)


class OnBoardMobileAppStepView(TemplateView):
    orgs = None
    org = None
    template_name = 'onboard/onboard-step-mobile.html'

    def get_context_data(self, **kwargs):
        context = super(OnBoardMobileAppStepView, self).get_context_data(**kwargs)

        context['step'] = 3
        context['title'] = _('Step 3. Download the IOTile Companion App')
        context['user'] = self.request.user
        context['orgs'] = self.orgs.order_by('name')
        context['next'] = reverse_lazy('onboard-step-claim')
        context['apple_id'] = '1142010560'
        context['google_id'] = 'com.archiot.iotileapp'
        context['welcome'] = False

        return context

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.orgs = Org.objects.user_orgs_qs(request.user)
        if not self.orgs.exists():
            msg = 'You need to setup your company first'
            messages.success(self.request, msg)
            return HttpResponseRedirect(reverse('onboard-step-org'))

        return super(OnBoardMobileAppStepView, self).dispatch(request, *args, **kwargs)


class OnBoardDeviceClaimStepView(TemplateView):
    orgs = None
    org = None
    template_name = 'onboard/onboard-step-claim.html'

    def get_context_data(self, **kwargs):
        context = super(OnBoardDeviceClaimStepView, self).get_context_data(**kwargs)

        context['step'] = 4
        context['title'] = _('Step 4. Use IOTile Companion App to claim your device')
        context['orgs'] = self.orgs.order_by('name')
        context['next'] = reverse_lazy('home')
        context['welcome'] = False

        return context

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.orgs = Org.objects.user_orgs_qs(request.user)
        if not self.orgs.exists():
            msg = 'You need to setup your company first'
            messages.success(self.request, msg)
            return HttpResponseRedirect(reverse('onboard-step-org'))

        return super(OnBoardDeviceClaimStepView, self).dispatch(request, *args, **kwargs)


class RobotView(TemplateView):
    template_name = 'robots.txt'


def i18n_javascript(request):
    return admin.site.i18n_javascript(request)


class CrossDomainView(TemplateView):
    template_name = 'crossdomain.xml'

    def get_context_data(self, **kwargs):
        context = super(CrossDomainView, self).get_context_data(**kwargs)
        domains = []
        host = self.request.get_host()
        if host:
            domains.append(host)
        cdn = getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', None)
        if cdn:
            domains.append(cdn)
        for d in getattr(settings, 'CORS_ORIGIN_WHITELIST'):
            domains.append(d)

        context['extra_domains'] = domains

        return context


class AboutView(TemplateView):
    template_name = 'main/about.html'
