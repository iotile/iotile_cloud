import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView, TemplateView, UpdateView
from django.views.generic.edit import CreateView, DeleteView, FormView

from allauth.account.models import EmailAddress

from apps.component.models import Component
from apps.component.views import ComponentAccessMixin
from apps.deviceauth.models import DeviceKey
from apps.devicetemplate.views import ProductAccessMixin
from apps.org.models import Org
from apps.org.views import OrgAccessMixin
from apps.ota.models import DeviceVersionAttribute
from apps.physicaldevice.data_utils import StreamDataCountHelper
from apps.physicaldevice.models import Device
from apps.physicaldevice.views import DeviceAccessMixin
from apps.sensorgraph.models import SensorGraph
from apps.stream.models import StreamId
from apps.streamdata.models import StreamData
from apps.streamer.models import StreamerReport
from apps.streamfilter.dynamodb import DynamoFilterLogModel
from apps.streamnote.models import StreamNote
from apps.utils.timezone_utils import convert_to_utc

from .forms import *

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL', 'auth.User')
FILTER_LOGS_LIMIT = 50
UPLOAD_EVENT_LIMIT = 100
USE_DYNAMODB_FILTERLOG_DB = getattr(settings, 'USE_DYNAMODB_FILTERLOG_DB')

# Get an instance of a logger
logger = logging.getLogger(__name__)
user_model = get_user_model()


class VendorAccessMixin(OrgAccessMixin):

    @method_decorator(login_required())
    def dispatch(self, *args, **kwargs):

        self.org = self.get_object()
        if not self.org.has_permission(self.request.user, 'can_manage_org_and_projects'):
            raise PermissionDenied
        return super(VendorAccessMixin, self).dispatch(*args, **kwargs)


class VendorDeviceAccessMixin(object):

    @method_decorator(login_required())
    def dispatch(self, *args, **kwargs):

        self.org = Org.objects.get(slug=self.kwargs['slug'])
        if not self.org.has_permission(self.request.user, 'can_manage_org_and_projects'):
            raise PermissionDenied
        return super(VendorDeviceAccessMixin, self).dispatch(*args, **kwargs)


class VendorIndexView(VendorAccessMixin, FormView):
    model = Org
    template_name = 'vendor/detail.html'
    form_class = GetDeviceForm

    def form_valid(self, form):
        org = Org.objects.get(slug=self.kwargs['slug'])
        d = form.cleaned_data['device_id']
        device = Device.objects.select_related('template').get(id=d.id)
        if device and device.template and device.template.org.slug == org.slug:
            return HttpResponseRedirect(reverse('vendor:device-detail', kwargs={'slug': org.slug, 'pk': d.pk}))
        # if no device found, display message
        messages.error(self.request, 'No device found')
        return HttpResponseRedirect(reverse('vendor:home', kwargs=self.kwargs))

    def get_context_data(self, **kwargs):
        self.object = self.get_object()
        context = super(VendorIndexView, self).get_context_data(**kwargs)

        # TODO: fix this to use proper permissions framework
        context.update(self.get_basic_context())

        context['membership_count'] = self.object.member_count()
        context['project_list'] = self.object.projects.all().order_by('name')
        context['fleet_list'] = self.object.fleets.order_by('name')
        context['webapp'] = getattr(settings, 'WEBAPP_BASE_URL')
        context['project_count'] = self.object.projects.count()
        context['device_count'] = self.object.templates.count()
        context['user_count'] = user_model.objects.count()

        # form
        context['form'] = self.get_form()
        context['org'] = self.object
        return context


class VendorMapView(VendorAccessMixin, TemplateView):
    template_name = 'staff/map.html'

    def get_context_data(self, **kwargs):
        context = super(VendorMapView, self).get_context_data(**kwargs)

        context['org'] = self.kwargs['slug']
        context['production'] = settings.PRODUCTION
        device_list = []
        for dt in DeviceTemplate.objects.filter(org__slug=self.kwargs['slug']):
            device_list.extend(Device.objects.filter(template__slug=dt.slug))

        context['devices'] = device_list
        context['api_key'] = getattr(settings, 'GOOGLE_API_KEY')

        return context


class VendorDeviceDetailView(VendorDeviceAccessMixin, DetailView):
    model = Device
    template_name = 'vendor/device-detail.html'

    def get_context_data(self, **kwargs):
        context = super(VendorDeviceDetailView, self).get_context_data(**kwargs)

        org = Org.objects.get(slug=self.kwargs['slug'])
        context['org'] = org

        streams = StreamId.objects.filter(device=self.object, block__isnull=True)
        context['stream_count'] = streams.count()

        context['data_counter'] = StreamDataCountHelper(self.object)

        # for the map
        context['devices'] = [self.object]
        context['api_key'] = getattr(settings, 'GOOGLE_API_KEY')
        context['reports'] = StreamerReport.objects.filter(streamer__device=self.object).order_by('-sent_timestamp')[:UPLOAD_EVENT_LIMIT]
        context['last_report'] = context['reports'].first()

        filter_logs = []
        if USE_DYNAMODB_FILTERLOG_DB:
            for stream in streams:
                try:
                    filter_logs += DynamoFilterLogModel.target_index.query(stream.slug, limit=FILTER_LOGS_LIMIT)
                except Exception as e:
                    logger.error(str(e))
        for log in filter_logs:
            try:
                log.timestamp = convert_to_utc(log.timestamp)
            except Exception:
                pass
        context['filter_logs'] = filter_logs

        context['device_system_logs'] = StreamNote.objects.filter(
            target_slug=self.object, type__in=['sc', 'si']).order_by('-timestamp')[:10]
        context['device_versions'] = DeviceVersionAttribute.objects.current_device_version_qs(self.object)

        context['device_key_count'] = DeviceKey.objects.filter(slug=self.object.slug).count()

        return context


class VendorProjectListView(VendorAccessMixin, DetailView):
    model = Org
    template_name = 'staff/project-list.html'# 'org/detail.html'

    def get_context_data(self, **kwargs):
        context = super(VendorProjectListView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        context['membership_count'] = self.object.member_count()
        context['object_list'] = self.object.projects.all().order_by('name')
        context['fleet_list'] = self.object.fleets.order_by('name')
        context['webapp'] = getattr(settings, 'WEBAPP_BASE_URL')
        return context


class VendorProductListView(ProductAccessMixin, ListView):
    model = DeviceTemplate
    template_name = 'devicetemplate/list.html'

    def get_queryset(self):
        return DeviceTemplate.objects.filter(org__slug=self.kwargs['slug'], active=True)

    def get_context_data(self, **kwargs):
        context = super(VendorProductListView, self).get_context_data(**kwargs)
        context['device_list'] = self.object_list
        context['is_staff'] = self.request.user.is_staff
        return context


class VendorSensorGraphMatrixView(VendorAccessMixin, ListView):
    model = Device
    template_name = 'staff/sg-matrix.html'

    def get_context_data(self, **kwargs):
        org = self.get_object()
        context = super(VendorSensorGraphMatrixView, self).get_context_data(**kwargs)
        context['org'] = org
        matrix = []
        for sg in SensorGraph.objects.filter(org__slug=org.slug):
            item = {
                'sg': sg,
                'all_devices': sg.devices.count(),
                'claimed_devices': sg.devices.filter(project__isnull=False).count(),
            }
            matrix.append(item)

        context['matrix'] = matrix
        return context


class VendorProductMatrixView(VendorAccessMixin, TemplateView):
    template_name = 'vendor/product-matrix.html'

    def get_context_data(self, **kwargs):
        org = self.get_object()
        context = super(VendorProductMatrixView, self).get_context_data(**kwargs)
        context['org'] = org
        matrix = []
        for dt in DeviceTemplate.objects.filter(org__slug=self.kwargs['slug']):
            item = {
                'template': dt,
                'all_devices': dt.devices.count(),
                'claimed_devices': dt.devices.filter(project__isnull=False).count(),
            }
            matrix.append(item)

        context['matrix'] = matrix
        return context
