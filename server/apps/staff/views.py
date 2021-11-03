import logging

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.mail import EmailMessage
from django.db.models import Count
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, ListView, TemplateView, UpdateView
from django.views.generic.edit import CreateView, DeleteView, FormView
from iotile_cloud.utils.gid import *

from apps.deviceauth.models import DeviceKey
from apps.org.models import Org, OrgMembership
from apps.ota.models import DeviceVersionAttribute
from apps.physicaldevice.claim_utils import device_claim, device_semiclaim, device_unclaim
from apps.physicaldevice.data_utils import StreamDataCountHelper
from apps.physicaldevice.models import Device, DeviceStatus
from apps.physicaldevice.serializers import DeviceStatusReadOnlySerializer
from apps.project.models import Project
from apps.project.utils import clone_project
# from apps.streamtimeseries.models import StreamTimeSeriesValue, StreamTimeSeriesEvent
from apps.utils.gid.convert import int16gid, formatted_gsid, int2vid
from apps.sensorgraph.models import SensorGraph
from apps.sqsworker.stats import WorkerStats
from apps.sqsworker.worker import WorkerHealthCheckAction
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.streamer.models import StreamerReport
from apps.streamfilter.dynamodb import DynamoFilterLogModel
from apps.streamfilter.models import StreamFilter, StreamFilterAction, StreamFilterTrigger
from apps.streamnote.models import StreamNote
from apps.utils.data_helpers.manager import DataManager
from apps.utils.fineuploader.sign import FineUploaderSignMixIn
from apps.utils.sms.helper import SmsHelper
from apps.utils.timezone_utils import convert_to_utc, str_utc
from apps.ota.models import DeviceVersionAttribute
# from apps.utils.data_helpers.convert import DataConverter

from .forms import *
from .worker.move_device_stream_data import MoveDeviceStreamDataAction
from .worker.staff_operations import StaffOperationsAction

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL', 'auth.User')
FILTER_LOGS_LIMIT = 50
UPLOAD_EVENT_LIMIT = 100
USE_DYNAMODB_FILTERLOG_DB = getattr(settings, 'USE_DYNAMODB_FILTERLOG_DB')

# Get an instance of a logger
logger = logging.getLogger(__name__)
user_model = get_user_model()


class StaffRequiredMixin(object):

    @method_decorator(login_required())
    def dispatch(self, *args, **kwargs):
        if not self.request.user.is_staff:
            raise PermissionDenied
        return super(StaffRequiredMixin, self).dispatch(*args, **kwargs)


class StaffIndexView(StaffRequiredMixin, FormView):
    template_name = 'staff/index.html'
    form_class = GetDeviceForm

    def form_valid(self, form):
        d = form.cleaned_data['device_id']
        if Device.objects.filter(id=d.id).exists():
            return HttpResponseRedirect(reverse('staff:device-detail', kwargs={'pk': d.pk}))
        # if no device found, display message
        messages.error(self.request, 'No device found')
        return HttpResponseRedirect(reverse('staff:home'))

    def get_context_data(self, **kwargs):
        context = super(StaffIndexView, self).get_context_data(**kwargs)

        context['production'] = settings.PRODUCTION
        context['user_count'] = user_model.objects.count()
        context['org_count'] = Org.objects.count()
        context['membership_count'] = OrgMembership.objects.count()
        context['orgs'] = Org.objects.all().order_by('name')[:50]
        context['project_count'] = Project.objects.count()
        context['device_count'] = Device.objects.count()
        context['stream_count'] = StreamId.objects.count()
        context['variable_count'] = StreamVariable.objects.count()
        context['stream_data_count'] = DataManager.count('data')
        context['devices'] = Device.objects.all()
        context['api_key'] = getattr(settings, 'GOOGLE_API_KEY')

        return context


class StaffMapView(StaffRequiredMixin, TemplateView):
    template_name = 'staff/map.html'

    def get_context_data(self, **kwargs):
        context = super(StaffMapView, self).get_context_data(**kwargs)

        context['production'] = settings.PRODUCTION
        context['devices'] = Device.objects.all()
        context['api_key'] = getattr(settings, 'GOOGLE_API_KEY')

        return context


class StaffDeviceDetailView(StaffRequiredMixin, DetailView):
    model = Device
    template_name = 'staff/device-detail.html'

    def get_context_data(self, **kwargs):
        context = super(StaffDeviceDetailView, self).get_context_data(**kwargs)

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


class StaffDeviceKeysDetailView(StaffRequiredMixin, DetailView):
    """View displaying a list of all the downloadable keys for a device"""
    model = Device
    template_name = 'staff/keys-list.html'

    def get_context_data(self, **kwargs):
        context = super(StaffDeviceKeysDetailView, self).get_context_data(**kwargs)

        # Gets every key for that device
        context['key_list'] = DeviceKey.objects.filter(slug=self.object.slug, downloadable=True)
        return context


class StaffStreamsView(StaffRequiredMixin, TemplateView):
    template_name = 'staff/streams.html'

    def get_context_data(self, **kwargs):
        context = super(StaffStreamsView, self).get_context_data(**kwargs)

        context['stream_data_count'] = DataManager.count('data')
        distinct_streams = DataManager.all_qs('data').order_by('stream_slug').values('stream_slug').annotate(total=Count('streamer_local_id'))

        stream_dict = {}
        count = 0
        for item in distinct_streams:
            count += 1
            stream_dict[item['stream_slug']] = item

        for streamid in StreamId.objects.all():
            if streamid.slug in stream_dict:
                stream_dict[streamid.slug]['has_streamid'] = True

        context['distinct_streams'] = stream_dict
        context['count'] = count

        return context


class StaffNewUserView(StaffRequiredMixin, FormView):
    template_name = 'staff/form.html'
    form_class = NewUserForm
    success_url = '/staff/'

    def form_valid(self, form):
        name = form.cleaned_data['name']
        username = form.cleaned_data['username']
        email = form.cleaned_data['email']
        temp_password = form.cleaned_data['temp_password']
        org = form.cleaned_data['org']
        msg = 'Successfully created new user @{0}'.format(username)

        # 1.- Create User
        new_user = user_model.objects.create_user(email=email, username=username, password=temp_password)
        new_user.name = name
        new_user.is_active = True
        new_user.save()

        # 2.- Also set email as verified
        EmailAddress.objects.create(email=email, user=new_user, verified=True, primary=True)

        # 3.- If needed, add new user as member of an Organization
        if org:
            OrgMembership.objects.create(user=new_user, org=org)
            msg += ' and adding to {0}'.format(org)

        logger.info(msg)
        messages.success(self.request, msg)

        return super(StaffNewUserView, self).form_valid(form)

    def get_context_data(self, **kwargs):
        context = super(StaffNewUserView, self).get_context_data(**kwargs)
        context['title'] = _('Create new User (No invitation)')
        return context


class StaffStreamDataDeleteView(StaffRequiredMixin, FormView):
    form_class = StaffStreamDataDeleteForm
    template_name = 'staff/form.html'

    def form_valid(self, form):
        base_url = reverse('staff:stream-data-delete-confirm', kwargs=self.kwargs)
        if 'delete_data' in self.request.POST:
            date_from_str = str_utc(form.cleaned_data['date_from']) if form.cleaned_data['date_from'] else ''
            date_to_str = str_utc(form.cleaned_data['date_to']) if form.cleaned_data['date_to'] else ''
            confirm_url = '{0}?from={1}&to={2}'.format(base_url, date_from_str, date_to_str)
        elif 'delete_all' in self.request.POST:
            confirm_url = '{0}?all=True'.format(base_url)
        return HttpResponseRedirect(confirm_url)

    def get_context_data(self, **kwargs):
        context = super(StaffStreamDataDeleteView, self).get_context_data(**kwargs)
        context['title'] = _('Delete Stream Data')
        context['stream_slug'] = self.kwargs['slug']
        streamid = StreamId.objects.filter(slug=self.kwargs['slug']).count()
        if streamid == 0:
            context['has_streamid'] = False
        else:
            context['has_streamid'] = True
        return context


class StaffStreamDataDeleteConfirmView(StaffRequiredMixin, FormView):
    form_class = StaffStreamDataDeleteConfirmForm
    template_name = 'staff/form.html'
    success_url = reverse_lazy('staff:home')

    def get(self, *arg, **kwargs):
        self.data_qs = self.get_stream_data()
        self.data_count = self.data_qs.count()
        self.event_qs = self.get_stream_event()
        self.event_count = self.event_qs.count()
        if 'from' in self.request.GET and 'to' in self.request.GET:
            if self.data_count == 0 and self.event_count == 0:
                messages.error(self.request, 'No data or event points match the dates your provided')
                return HttpResponseRedirect(reverse('staff:stream-data-delete', kwargs=kwargs))
        return super(StaffStreamDataDeleteConfirmView, self).get(*arg, **kwargs)

    def get_stream_data(self):
        if 'all' in self.request.GET:
            data_qs = DataManager.filter_qs('data', stream_slug=self.kwargs['slug'])
        elif 'from' in self.request.GET and 'to' in self.request.GET:
            date_from_str = self.request.GET['from'] if self.request.GET['from'] else '1970-01-01T00:00:00Z'
            date_to_str = self.request.GET['to'] if self.request.GET['to'] else '2200-01-01T00:00:00Z'
            data_qs = DataManager.filter_qs('data', stream_slug=self.kwargs['slug'], timestamp__lte=date_to_str, timestamp__gte=date_from_str)
        else:
            data_qs = None
        return data_qs

    def get_stream_event(self):
        if 'all' in self.request.GET:
            event_qs = DataManager.filter_qs('event', stream_slug=self.kwargs['slug'])
        elif 'from' in self.request.GET and 'to' in self.request.GET:
            date_from_str = self.request.GET['from'] if self.request.GET['from'] else '1970-01-01T00:00:00Z'
            date_to_str = self.request.GET['to'] if self.request.GET['to'] else '2200-01-01T00:00:00Z'
            event_qs = DataManager.filter_qs('event', stream_slug=self.kwargs['slug'], timestamp__lte=date_to_str, timestamp__gte=date_from_str)
        else:
            event_qs = None
        return event_qs

    def form_valid(self, form):
        data_qs = self.get_stream_data()
        if data_qs:
            data_qs.delete()
        event_qs = self.get_stream_event()
        if event_qs:
            event_qs.delete()
        if 'all' in self.request.GET:
            StreamId.objects.filter(slug=self.kwargs['slug']).delete()
        messages.success(self.request, 'Stream has been deleted')
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(StaffStreamDataDeleteConfirmView, self).get_context_data(**kwargs)
        context['stream_slug'] = self.kwargs['slug']
        context['data_count'] = self.data_count
        context['event_count'] = self.event_count
        context['all'] = 'all' in self.request.GET
        context['title'] = _('Delete {0} stream data and {1} stream event entries ?').format(self.data_count, self.event_count)
        if 'from' in self.request.GET and self.request.GET['from']:
            context['from_parse_iso'] = parse_datetime(self.request.GET['from']).isoformat()
        else:
            context['from_parse_iso'] = ''
        if 'to' in self.request.GET and self.request.GET['to']:
            context['to_parse_iso'] = parse_datetime(self.request.GET['to']).isoformat()
        else:
            context['to_parse_iso'] = ''
        context['data_qs'] = self.data_qs
        context['event_qs'] = self.event_qs
        context['current_timezone'] = timezone.get_current_timezone_name()
        return context


class StaffStreamerReportUploadView(StaffRequiredMixin, TemplateView):
    template_name = 'staff/stream-uploader.html'

    def get_context_data(self, **kwargs):
        context = super(StaffStreamerReportUploadView, self).get_context_data(**kwargs)

        context['fineuploader_request_endpoint'] = settings.STREAMER_REPORT_DROPBOX_ENDPOINT
        context['fineuploader_accesskey'] = settings.STREAMER_REPORT_DROPBOX_PUBLIC_KEY
        context['fineuploader_success_endpoint'] = reverse('staff:streamer-report-upload-success')
        context['fineuploader_signature_endpoint'] = reverse('staff:streamer-report-upload-signee')
        context['fineuploader_max_size'] = settings.STREAMER_REPORT_DROPBOX_MAX_SIZE
        context['fineuploader_item_limit'] = 1
        context['fineuploader_extensions'] = 'bin'

        now = str_utc(timezone.now())
        # incoming/2016-09-19/<file>
        key_path = settings.STREAMER_REPORT_DROPBOX_KEY_FORMAT.format(username=self.request.user.username, date=now)
        context['fineuploader_storage_dirname'] = key_path

        return context


# Create your views here.
class StaffStreamerReportUploadSuccessEndpointView(View):
    http_method_names = ['post', ]

    def post(self, request, *args, **kwargs):
        """ This is where the upload will send a POST request after the
        file has been stored in S3.
        """
        # Note that Fine Uploader will still send the bucket, key, filename, UUID, and etag (if available) as well

        response = HttpResponse()
        if not (self.request.POST.get(u'name') and self.request.POST.get(u'key') and self.request.POST.get(u'uuid')):
            response.status_code = 405
            return response

        name = self.request.POST.get(u'name')
        key = self.request.POST.get(u'key')
        uuid = self.request.POST.get(u'uuid')

        # DO SOMETHING
        logger.info('Uploaded json file successfully: name={0}, key={1}, uuid={2}'.format(name, key, uuid))

        response.status_code = 200
        response['Content-Type'] = "application/json"
        response_data = {
            'redirectURL': reverse('staff:home')
        }
        response.content = json.dumps(response_data)
        messages.success(request, 'File has been uploaded and scheduled for processing')

        return response

    @method_decorator(login_required)
    @csrf_exempt
    def dispatch(self, request, *args, **kwargs):
        return super(StaffStreamerReportUploadSuccessEndpointView, self).dispatch(request, *args, **kwargs)


class StaffStreamerReportUploadHandleS3View(FineUploaderSignMixIn, StaffRequiredMixin, View):
    private_key = settings.STREAMER_REPORT_DROPBOX_PRIVATE_KEY
    bucket_name = settings.STREAMER_REPORT_DROPBOX_BUCKET_NAME
    max_size = settings.STREAMER_REPORT_DROPBOX_MAX_SIZE


class StaffProjectMoveConfirmView(StaffRequiredMixin, FormView):
    template_name = 'staff/form.html'
    success_url = '/staff/'
    form_class = MoveProjectConfirmForm
    project_id = None

    def form_valid(self, form):
        project = get_object_or_404(Project, pk=self.project_id)
        new_org = get_object_or_404(Org, slug=self.new_org)
        name = project.name
        devices = Device.objects.filter(project=project)
        messages.success(self.request, "Moving {} devices".format(devices.count()))
        for d in devices:
            d.org = new_org
            d.save()
        variables = StreamVariable.objects.filter(project=project)
        messages.success(self.request, "Moving {} stream variables".format(variables.count()))
        for v in variables:
            v.org = new_org
            v.save()
        streams = StreamId.objects.filter(project=project)
        messages.success(self.request, "Moving {} streams".format(streams.count()))
        for s in streams:
            s.org = new_org
            s.save()
        project = Project.objects.filter(id=self.project_id)
        p = project.first()
        p.org = new_org
        p.save()
        messages.success(self.request, 'Successfully moved project {}'.format(name))
        return super(StaffProjectMoveConfirmView, self).form_valid(form)

    def get(self, request, *args, **kwargs):
        self.project_id = kwargs['pk']
        self.new_org = kwargs['org_slug']
        return super(StaffProjectMoveConfirmView, self).get(self, request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.project_id = kwargs['pk']
        self.new_org = kwargs['org_slug']
        return super(StaffProjectMoveConfirmView, self).post(self, request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(StaffProjectMoveConfirmView, self).get_context_data(**kwargs)
        project = get_object_or_404(Project, pk=self.project_id)
        new_org = get_object_or_404(Org, slug=self.new_org)
        context['title'] = _('Move Confirmation')
        context['project'] = project
        context['new_org'] = new_org
        device_stream = {}
        devices = Device.objects.filter(project=project)
        for d in devices:
            device_stream[d.slug] = StreamId.objects.filter(device=d).values()
        context['device_stream'] = device_stream
        context['variables'] = StreamVariable.objects.filter(project=project).values()
        return context


class StaffProjectMoveView(StaffRequiredMixin, FormView):
    template_name = 'staff/form.html'
    form_class = MoveProjectForm
    success_url = '/staff/'

    def form_valid(self, form):
        project = form.cleaned_data['project']
        org = form.cleaned_data['new_org']
        return HttpResponseRedirect(reverse('staff:project-move-confirm', kwargs={'pk': str(project.id), 'org_slug': org.slug}))


class StaffProjectDeleteView(StaffRequiredMixin, FormView):
    template_name = 'staff/form.html'
    form_class = DeleteProjectForm
    success_url = '/staff/'

    def form_valid(self, form):
        project = form.cleaned_data['project']
        return HttpResponseRedirect(reverse('staff:project-delete-confirm', kwargs={'pk': str(project.id)}))


class StaffProjectDeleteConfirmView(StaffRequiredMixin, FormView):
    template_name = 'staff/form.html'
    success_url = '/staff/'
    form_class = DeleteProjectConfirmForm
    project_id = None

    def form_valid(self, form):
        project = get_object_or_404(Project, pk=self.project_id)
        name = project.name
        devices = Device.objects.filter(project=project)
        for d in devices:
            msg = device_unclaim(device=d, clean_streams=True)
            messages.success(self.request, msg)
        variables = StreamVariable.objects.filter(project=project)
        messages.success(self.request, "Deleting {} stream variables".format(variables.count()))
        variables.delete()
        Project.objects.filter(id=self.project_id).delete()
        messages.success(self.request, 'Successful deleted project {}'.format(name))
        return super(StaffProjectDeleteConfirmView, self).form_valid(form)

    def get(self, request, *args, **kwargs):
        self.project_id = kwargs['pk']
        return super(StaffProjectDeleteConfirmView, self).get(self, request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.project_id = kwargs['pk']
        return super(StaffProjectDeleteConfirmView, self).post(self, request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(StaffProjectDeleteConfirmView, self).get_context_data(**kwargs)
        project = get_object_or_404(Project, pk=self.project_id)
        context['title'] = _('Delete Confirmation')
        context['project'] = project
        device_stream = {}
        devices = Device.objects.filter(project=project)
        for d in devices:
            device_stream[d.slug] = StreamId.objects.filter(device=d).values()
        context['device_stream'] = device_stream
        context['variables'] = StreamVariable.objects.filter(project=project).values()
        return context


class StaffCreateDeviceBatchView(StaffRequiredMixin, FormView):
    template_name = 'staff/form.html'
    form_class = DeviceBatchForm
    success_url = '/staff/iotile/batch/'

    def form_valid(self, form):
        operation_args = {
            'template': form.cleaned_data['template'].slug,
            'sg': form.cleaned_data['sg'].slug,
            'org': '',
            'name_format': form.cleaned_data['name_format'],
            'num_devices': form.cleaned_data['num_devices']
        }
        msg = 'Successfully scheduled task to create  {0} \'{1}\' devices with SG {2}'.format(
            form.cleaned_data['num_devices'], form.cleaned_data['template'], form.cleaned_data['sg']
        )

        payload = {
            'operation': 'create_devices',
            'user': self.request.user.slug,
            'args': operation_args
        }
        StaffOperationsAction.schedule(payload)

        messages.success(self.request, msg)
        super(StaffCreateDeviceBatchView, self).form_valid(form)
        return HttpResponseRedirect(reverse('staff:home'))


class StaffBatchUpgradeSgView(StaffRequiredMixin, FormView):
    form_class = BatchUpgradeSgForm
    template_name = 'staff/form.html'
    success_url = '/staff'

    def get_context_data(self, **kwargs):
        context = super(StaffBatchUpgradeSgView, self).get_context_data(**kwargs)
        context['title'] = "Batch Upgrade Sensor Graph"
        return context

    def form_valid(self, form):
        sg_from = form.cleaned_data['sg_from']
        sg_to = form.cleaned_data['sg_to']
        super(StaffBatchUpgradeSgView, self).form_valid(form)
        return HttpResponseRedirect(reverse('staff:upgrade-sg-batch-confirm', kwargs={'pk_from': sg_from.pk, 'pk_to': sg_to.pk}))


class StaffBatchUpgradeSgConfirmView(StaffRequiredMixin, FormView):
    form_class = BatchUpgradeSgConfirmForm
    template_name = 'staff/form.html'
    success_url = '/staff/'
    sg_from = None
    sg_to = None

    def get(self, *arg, **kwargs):
        self.sg_from = SensorGraph.objects.get(pk=kwargs['pk_from'])
        self.sg_to = SensorGraph.objects.get(pk=kwargs['pk_to'])
        return super(StaffBatchUpgradeSgConfirmView, self).get(*arg, **kwargs)

    def post(self, *arg, **kwargs):
        self.sg_from = SensorGraph.objects.get(pk=kwargs['pk_from'])
        self.sg_to = SensorGraph.objects.get(pk=kwargs['pk_to'])
        return super(StaffBatchUpgradeSgConfirmView, self).post(*arg, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(StaffBatchUpgradeSgConfirmView, self).get_context_data(**kwargs)
        devices = Device.objects.filter(sg=self.sg_from)
        context['title'] = "Batch Upgrade Sensor Graph Confirmation"
        context['devices'] = devices
        context['total'] = len(devices)
        context['sg_from'] = self.sg_from.slug
        context['sg_to'] = self.sg_to.slug
        return context

    def form_valid(self, form):
        devices = self.sg_from.devices.all()
        num_devices = devices.count()
        devices.update(sg=self.sg_to)
        messages.success(self.request, "Successfully upgraded {0} devices from sensor graph {1} to {2}".format(num_devices, self.sg_from.slug, self.sg_to.slug))
        super(StaffBatchUpgradeSgConfirmView, self).form_valid(form)
        return render(self.request, "staff/batch-summary.html", {'devices': self.sg_to.devices.all(),
                                                                 'label': 'Sensor Grpah',
                                                                 'new_value': self.sg_to,
                                                                 'title': "Upgraded devices",
                                                                 'num': num_devices})


class TestEmailView(StaffRequiredMixin, FormView):
    template_name = 'staff/form.html'
    form_class = TestEmailForm
    success_url = '/staff/'

    def form_valid(self, form):
        email_to = form.cleaned_data['email']
        msg = 'Successfully sent email to {0}'.format(email_to)

        email_subject = 'Email Test'
        email_msg = 'This is an email test from https://iotile.cloud'

        email = EmailMessage(
            subject=email_subject,
            body=email_msg,
            to=[email_to, ],
        )
        email.send(fail_silently=True)

        logger.info(msg)
        messages.success(self.request, msg)

        return super(TestEmailView, self).form_valid(form)

    def get_context_data(self, **kwargs):
        context = super(TestEmailView, self).get_context_data(**kwargs)
        context['title'] = _('Email Infrastructure Test')
        return context


class StaffDeviceSemiClaimConfirmView(StaffRequiredMixin, UpdateView):
    model = Device
    template_name = 'staff/form.html'
    form_class = DeviceSemiClaimConfirmForm
    success_url = '/staff/'

    def form_valid(self, form):
        device = self.object
        org = form.cleaned_data['dst_org']

        if device.project is not None:
            messages.error(self.request, f'Device already claimed. Belongs to \'{device.project}\'')

        if device.org is None:
            device_semiclaim(device=device, org=org)
            messages.success(self.request, f'Device Semi-claimed (org={org})')
        else:
            messages.error(self.request, f'Device cannot be claimed. Belongs to \'{device.org}\'')

        super().form_valid(form)
        return HttpResponseRedirect(reverse('staff:device-detail', kwargs={'pk': self.object.pk}))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        device = self.object
        context['device'] = device
        context['title'] = _('Are you sure you want to claim device {0}?'.format(device.slug))
        return context


class StaffDeviceClaimConfirmView(StaffRequiredMixin, UpdateView):
    model = Device
    template_name = 'staff/form.html'
    form_class = DeviceClaimConfirmForm
    success_url = '/staff/'

    def form_valid(self, form):
        device = self.object
        project = form.cleaned_data['dst_project']
        claimed_by = form.cleaned_data['claimed_by']

        if device.project == None:
            device.set_active_from_state()
            device.save()
            device_claim(device=device, project=project, claimed_by=claimed_by)
            messages.success(self.request, 'Device Claimed')
        else:
            messages.error(self.request, 'Device cannot be claimed. Belongs to \'{}\''.format(device.project))

        super(StaffDeviceClaimConfirmView, self).form_valid(form)
        return HttpResponseRedirect(reverse('staff:device-detail', kwargs={'pk': self.object.pk}))

    def get_context_data(self, **kwargs):
        context = super(StaffDeviceClaimConfirmView, self).get_context_data(**kwargs)
        device = self.object
        context['device'] = device
        context['title'] = _('Are you sure you want to claim device {0}?'.format(device.slug))
        return context


class StaffDeviceUnclaimConfirmView(StaffRequiredMixin, UpdateView):
    model = Device
    template_name = 'staff/form.html'
    form_class = DeviceUnclaimConfirmForm

    def form_valid(self, form):
        device = self.object

        operation_args = {
            'device': device.slug,
            'clean_streams': form.cleaned_data['clean_streams'],
        }
        payload = {
            'operation': 'unclaim_device',
            'user': self.request.user.slug,
            'args': operation_args
        }
        StaffOperationsAction.schedule(payload)
        messages.success(self.request, "Scheduled task to unclaim device {0}".format(device))
        super(StaffDeviceUnclaimConfirmView, self).form_valid(form)

        return HttpResponseRedirect(reverse('staff:device-detail', kwargs={'pk': self.object.pk}))

    def get_context_data(self, **kwargs):
        context = super(StaffDeviceUnclaimConfirmView, self).get_context_data(**kwargs)
        device = self.object
        context['device'] = device
        context['properties'] = device.get_properties_qs().count()
        context['title'] = _('Are you sure you want to unclaim device {0}?'.format(device.slug))
        return context


class StaffDeviceUpgradeConfigView(StaffRequiredMixin, UpdateView):
    model = Device
    template_name = 'staff/form.html'
    form_class = UpgradeDeviceConfigForm

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.set_active_from_state()
        self.object.save()

        return HttpResponseRedirect(reverse('staff:device-detail', kwargs={'pk': self.object.pk}))

    def get_context_data(self, **kwargs):
        context = super(StaffDeviceUpgradeConfigView, self).get_context_data(**kwargs)
        device = self.object
        context['device'] = device
        context['title'] = _('Are you sure you want to SG and/or DT for device {0}?'.format(device.slug))
        return context


class StaffUserListView(StaffRequiredMixin, ListView):
    model = user_model
    template_name = 'staff/user-list.html'
    query_set = user_model.objects.all()


class StaffUserDetailView(StaffRequiredMixin, DetailView):
    model = user_model
    template_name = 'staff/user-detail.html'

    def get_context_data(self, **kwargs):
        context = super(StaffUserDetailView, self).get_context_data(**kwargs)
        membership = OrgMembership.objects.filter(user=self.object).select_related('org')
        orgs = Org.objects.filter(id__in=[m.org.id for m in membership])
        context['user_orgs'] = orgs
        context['claimed_devices'] = Device.objects.filter(claimed_by=self.object)
        context['last_report'] = StreamerReport.objects.filter(created_by=self.object).order_by('-sent_timestamp').first()
        context['membership'] = membership
        context['user_devices'] = Device.objects.user_device_qs(user=self.object)
        return context


class StaffOrgListView(StaffRequiredMixin, ListView):
    model = Org
    template_name = 'staff/org-list.html'
    query_set = Org.objects.all()


class StaffOrgDetailView(StaffRequiredMixin, DetailView):
    model = Org
    template_name = 'staff/org-detail.html'

    def get_context_data(self, **kwargs):
        context = super(StaffOrgDetailView, self).get_context_data(**kwargs)
        context['members'] = OrgMembership.objects.filter(org=self.object).select_related('user')
        context['devices'] = self.object.devices.order_by('-claimed_on').select_related('created_by', 'project')
        context['projects'] = self.object.projects.all().select_related('created_by', 'project_template')
        return context


class StaffProjectListView(StaffRequiredMixin, ListView):
    model = Project
    template_name = 'staff/project-list.html'
    query_set = Project.objects.all().select_related('org')


class StaffProjectDetailView(StaffRequiredMixin, DetailView):
    model = Project
    template_name = 'staff/project-detail.html'

    def get_query_object(self, **kwargs):
        project = get_object_or_404(Project, pk=kwargs['pk'])
        return project

    def get_context_data(self, **kwargs):
        context = super(StaffProjectDetailView, self).get_context_data(**kwargs)
        context['devices'] = Device.objects.filter(project=self.object)
        return context


class StaffOpsStatusView(StaffRequiredMixin, FormView):
    model = Project
    template_name = 'staff/ops-status.html'
    form_class = PingWorkerForm

    def form_valid(self, form):
        msg = 'Pinged on {}'.format(timezone.now())
        WorkerHealthCheckAction.schedule(args={'message': msg})
        messages.info(self.request, msg)
        return HttpResponseRedirect(reverse('staff:worker:home'))

    def get_context_data(self, **kwargs):
        context = super(StaffOpsStatusView, self).get_context_data(**kwargs)
        context['stats'] = WorkerStats()
        date_from_str = str_utc(timezone.now())
        context['utc_now'] = date_from_str
        context['future_data_count'] = DataManager.filter_qs('data', timestamp__gte=date_from_str).count()

        return context


class StaffGatewayStatusView(StaffRequiredMixin, ListView):
    model = Device
    template_name = 'staff/gateway-status.html'

    def get_context_data(self, **kwargs):
        context = super(StaffGatewayStatusView, self).get_context_data(**kwargs)
        devices = []
        device_qs = Device.objects.filter(sg__name="Gateway").exclude(project__isnull=True)
        for obj in DeviceStatus.objects.filter(device__in=[d.id for d in device_qs]):
            dev = {
                'id': obj.device.id,
                'slug': obj.device.slug,
                'org': obj.device.org,
                'project': obj.device.project,
                'status': obj
            }
            devices.append(dev)
        context['object_list'] = devices
        return context


class StaffDeviceFilterView(StaffRequiredMixin, DetailView):
    model = Device
    template_name = 'staff/device-filter-list.html'

    def get(self, *args, **kwargs):
        device = Device.objects.get(pk=kwargs['pk'])
        if device.project:
            return super(StaffDeviceFilterView, self).get(*args, **kwargs)
        else:
            messages.error(self.request, "Device must be claimed to set up filter")
            return HttpResponseRedirect(reverse('staff:device-detail', kwargs=kwargs))

    def _get_filter_list_for_device(self):
        streams = StreamId.objects.filter(device=self.object, block__isnull=True,
                                          project=self.object.project)
        filters = {}
        for stream in streams:
            elements = stream.slug.split('--')
            filter_stream_key = '--'.join(['f', ] + elements[1:])
            try:
                # If 2 filters (project and device) are defined for one stream, take the filter of the device first
                filters[stream.slug] = {'filter': StreamFilter.objects.get(slug=filter_stream_key), 'is_project_filter': False}
            except StreamFilter.DoesNotExist:
                # Check for project-wide filter
                filter_project_key = '--'.join(['f', elements[1], '', elements[3]])
                try:
                    filters[stream.slug] = {'filter': StreamFilter.objects.get(slug=filter_project_key), 'is_project_filter': True}
                except StreamFilter.DoesNotExist:
                    pass
        return filters

    def get_context_data(self, **kwargs):
        context = super(StaffDeviceFilterView, self).get_context_data(**kwargs)
        context['filters'] = self._get_filter_list_for_device()
        return context


class StaffDeviceDataMoveConfirmView(StaffRequiredMixin, FormView):
    template_name = 'staff/form.html'
    success_url = '/staff/'
    form_class = MoveDeviceDataConfirmForm
    project_id = None

    def form_valid(self, form):
        dev0 = get_object_or_404(Device, pk=self.dev0_id)
        dev1 = get_object_or_404(Device, pk=self.dev1_id)
        start = self.request.GET.get('start', None)
        end = self.request.GET.get('end', None)
        args = {
            'dev0_slug': dev0.slug,
            'dev1_slug': dev1.slug
        }
        if start:
            args['start'] = start
        if end:
            args['end'] = end
        MoveDeviceStreamDataAction.schedule(args=args)
        messages.success(self.request, "Scheduled task to moved {0} device data to {1}".format(dev0, dev1))
        return super(StaffDeviceDataMoveConfirmView, self).form_valid(form)

    def get(self, request, *args, **kwargs):
        self.dev0_id = kwargs['dev0']
        self.dev1_id = kwargs['dev1']
        return super(StaffDeviceDataMoveConfirmView, self).get(self, request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.dev0_id = kwargs['dev0']
        self.dev1_id = kwargs['dev1']
        return super(StaffDeviceDataMoveConfirmView, self).post(self, request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(StaffDeviceDataMoveConfirmView, self).get_context_data(**kwargs)
        dev0 = get_object_or_404(Device, pk=self.dev0_id)
        dev1 = get_object_or_404(Device, pk=self.dev1_id)
        context['title'] = _('Move Confirmation')
        context['dev0'] = dev0
        context['dev1'] = dev1
        device_stream = {}
        for d in [dev0, ]:
            device_stream[d.slug] = StreamId.objects.filter(device=d).values()
        context['device_stream'] = device_stream
        context['start'] = self.request.GET.get('start', None)
        context['end'] = self.request.GET.get('end', None)
        return context


class StaffDeviceDataMoveView(StaffRequiredMixin, FormView):
    template_name = 'staff/form.html'
    form_class = MoveDeviceDataForm
    success_url = '/staff/'

    def form_valid(self, form):
        dev0 = form.cleaned_data['dev0']
        dev1 = form.cleaned_data['dev1']
        start = form.cleaned_data['start']
        end = form.cleaned_data['end']
        url = reverse('staff:device-data-move-confirm', kwargs={'dev0': dev0.id, 'dev1': dev1.id})
        args = []
        if start:
            args.append('start={}'.format(str_utc(start)))
        if end:
            args.append('end={}'.format(str_utc(end)))
        if args:
            url += '?{}'.format('&'.join(args))
        return HttpResponseRedirect(url)


class StaffSensorGraphMatrixView(StaffRequiredMixin, ListView):
    model = Device
    template_name = 'staff/sg-matrix.html'

    def get_context_data(self, **kwargs):
        context = super(StaffSensorGraphMatrixView, self).get_context_data(**kwargs)
        matrix = []
        for sg in SensorGraph.objects.all():
            item = {
                'sg': sg,
                'all_devices': sg.devices.count(),
                'claimed_devices': sg.devices.filter(project__isnull=False).count(),
            }
            matrix.append(item)

        context['matrix'] = matrix
        return context


class StaffDeviceResetKeysConfirmView(StaffRequiredMixin, UpdateView):
    model = Device
    template_name = 'staff/form.html'
    form_class = DeviceResetKeysConfirmForm

    def form_valid(self, form):
        device = self.object

        count = DeviceKey.objects.filter(slug=device.slug).count()
        DeviceKey.objects.filter(slug=device.slug).delete()
        messages.success(self.request, '{} Device Keys have been deleted'.format(count))

        super(StaffDeviceResetKeysConfirmView, self).form_valid(form)
        return HttpResponseRedirect(reverse('staff:device-detail', kwargs={'pk': self.object.pk}))

    def get_context_data(self, **kwargs):
        context = super(StaffDeviceResetKeysConfirmView, self).get_context_data(**kwargs)
        device = self.object
        context['device'] = device
        context['keys'] = DeviceKey.objects.filter(slug=device.slug)
        context['title'] = _('Are you sure you want to reset device keys for {0}?'.format(device.slug))
        return context


class StaffOpsCacheView(StaffRequiredMixin, FormView):
    model = Project
    template_name = 'staff/ops-cache.html'
    form_class = CacheSearchForm

    def form_valid(self, form):
        return HttpResponseRedirect(reverse('staff:staff:ops-cache'))

    def get_context_data(self, **kwargs):
        context = super(StaffOpsCacheView, self).get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q')
        if context['q'] and cache:
            key_iter = cache.iter_keys(context['q'])
            results = []
            count = 0
            context['limit'] = 100
            while count < context['limit']:
                try:
                    key = next(key_iter)
                    count += 1
                    result = {
                        'key': key,
                        'value': cache.get(key)
                    }
                    results.append(result)
                except Exception:
                    context['count'] = context['limit']
                    break

            context['results'] = results
            context['count'] = count

        return context


class StaffSmsSendView(StaffRequiredMixin, FormView):
    template_name = 'staff/form.html'
    form_class = SmsSendForm
    success_url = '/staff/'

    def form_valid(self, form):
        number = form.cleaned_data['phone_number']
        msg = form.cleaned_data['msg']

        sms_helper = SmsHelper()
        ok, resp = sms_helper.send(to_number=number, body=msg)
        if ok:
            messages.success(self.request, 'Message sent. ID: {}'.format(resp))
        else:
            messages.error(self.request, 'ERROR: {}'.format(resp))

        return HttpResponseRedirect(reverse('staff:ops-status'))

    def get_context_data(self, **kwargs):
        context = super(StaffSmsSendView, self).get_context_data(**kwargs)
        context['title'] = _('Test SMS Send Infrastructure')
        sms_helper = SmsHelper()
        context['from_number'] = sms_helper.from_number
        return context


class StaffBatchUpgradeDeviceTemplateView(StaffRequiredMixin, FormView):
    form_class = BatchUpgradeDeviceTemplateForm
    template_name = 'staff/form.html'
    success_url = '/staff'

    def get_context_data(self, **kwargs):
        context = super(StaffBatchUpgradeDeviceTemplateView, self).get_context_data(**kwargs)
        context['title'] = "Batch Upgrade Device Template"
        return context

    def form_valid(self, form):
        dt_from = form.cleaned_data['dt_from']
        dt_to = form.cleaned_data['dt_to']
        super(StaffBatchUpgradeDeviceTemplateView, self).form_valid(form)
        return HttpResponseRedirect(reverse('staff:upgrade-dt-batch-confirm', kwargs={
            'pk_from': dt_from.pk, 'pk_to': dt_to.pk
        }))


class StaffBatchUpgradeDeviceTemplateConfirmView(StaffRequiredMixin, FormView):
    form_class = BatchUpgradeDeviceTemplateConfirmForm
    template_name = 'staff/form.html'
    success_url = '/staff/'
    dt_from = None
    dt_to = None

    def get(self, *arg, **kwargs):
        self.dt_from = DeviceTemplate.objects.get(pk=kwargs['pk_from'])
        self.dt_to = DeviceTemplate.objects.get(pk=kwargs['pk_to'])
        return super(StaffBatchUpgradeDeviceTemplateConfirmView, self).get(*arg, **kwargs)

    def post(self, *arg, **kwargs):
        self.dt_from = DeviceTemplate.objects.get(pk=kwargs['pk_from'])
        self.dt_to = DeviceTemplate.objects.get(pk=kwargs['pk_to'])
        return super(StaffBatchUpgradeDeviceTemplateConfirmView, self).post(*arg, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(StaffBatchUpgradeDeviceTemplateConfirmView, self).get_context_data(**kwargs)
        devices = Device.objects.filter(template=self.dt_from)
        context['title'] = "Batch Upgrade Device Template Confirmation"
        context['devices'] = devices
        context['total'] = len(devices)
        context['dt_from'] = self.dt_from.slug
        context['dt_to'] = self.dt_to.slug
        return context

    def form_valid(self, form):
        devices = self.dt_from.devices.all()
        num_devices = devices.count()
        devices.update(template=self.dt_to)
        messages.success(self.request, "Successfully upgraded {0} devices from Product {1} to {2}".format(num_devices, self.dt_from.slug, self.dt_to.slug))
        super(StaffBatchUpgradeDeviceTemplateConfirmView, self).form_valid(form)
        return render(self.request, "staff/batch-summary.html", {'devices': self.dt_to.devices.all(),
                                                                 'label': 'Device Template',
                                                                 'new_value': self.dt_to,
                                                                 'title': "Upgraded devices",
                                                                 'num': num_devices})


# class StaffStreamTimeSeriesMigrateDataView(StaffRequiredMixin, FormView):
#     model = StreamData
#     template_name = 'staff/form.html'
#     form_class = StreamTimeSeriesMigrateForm

#     def _migrate_data(self, streamdata_id):
#         streamdata = StreamData.objects.get(id=streamdata_id)
#         timeseries = DataConverter.data_to_tsvalue(streamdata)
#         timeseries.save()
#         return timeseries.id

#     def form_valid(self, form):
#         streamdata_id = form.cleaned_data['stream_id']
#         timeseriesvalue_id = self._migrate_data(streamdata_id)
#         redirect_url = reverse('staff:streamtimeseriesvalue-detail', kwargs={'pk': timeseriesvalue_id}) \
#             + '?data_ref={}'.format(streamdata_id)
#         return HttpResponseRedirect(redirect_url)

#     def get_context_data(self, **kwargs):
#         context = super(StaffStreamTimeSeriesMigrateDataView, self).get_context_data(**kwargs)
#         context['title'] = 'Migrate one StreamData point to the new model'
#         context['old_model'] = 'StreamData'
#         context['new_model'] = 'StreamTimeSeriesValue'
#         return context


# class StaffStreamTimeSeriesValueDetailView(StaffRequiredMixin, DetailView):
#     model = StreamTimeSeriesValue
#     template_name = 'staff/streamtimeseriesvalue-detail.html'

#     def _add_timestamp_formats(self, *args):
#         for obj in args:
#             if obj is not None:
#                 obj_dt = obj.timestamp
#                 obj.timezone = obj_dt.tzinfo
#                 obj.raw_timestamp = obj_dt.timestamp()

#     def get(self, request, *args, **kwargs):
#         self._streamdata_id = self.request.GET.get('data_ref')
#         return super(StaffStreamTimeSeriesValueDetailView, self).get(self, request, *args, **kwargs)

#     def get_context_data(self, *args, **kwargs):
#         context = super(StaffStreamTimeSeriesValueDetailView, self).get_context_data(*args, **kwargs)
#         timeseriesvalue = self.get_object()
#         if self._streamdata_id:
#             streamdata = get_object_or_404(StreamData, pk=self._streamdata_id)
#         else:
#             streamdata = None
#         self._add_timestamp_formats(streamdata, timeseriesvalue)
#         # use int2vid to display block_id
#         timeseriesvalue.block_vid = int2vid(timeseriesvalue.block_id) if timeseriesvalue.block_id else None
#         context['timeseriesvalue'] = timeseriesvalue
#         context['streamdata'] = streamdata
#         context['user_timezone'] = self.request.user.time_zone
#         return context


# class StaffStreamTimeSeriesMigrateEventView(StaffRequiredMixin, FormView):
#     model = StreamEventData
#     template_name = 'staff/form.html'
#     form_class = StreamTimeSeriesMigrateForm

#     def _migrate_event(self, streamevent_id):
#         streamevent = StreamEventData.objects.get(id=streamevent_id)
#         timeseries = DataConverter.event_to_tsevent(streamevent)
#         timeseries.save()
#         return timeseries.id

#     def form_valid(self, form):
#         streamevent_id = form.cleaned_data['stream_id']
#         timeseriesevent_id = self._migrate_event(streamevent_id)
#         redirect_url = reverse('staff:streamtimeseriesevent-detail', kwargs={'pk': timeseriesevent_id}) \
#             + '?event_ref={}'.format(streamevent_id)
#         return HttpResponseRedirect(redirect_url)

#     def get_context_data(self, **kwargs):
#         context = super(StaffStreamTimeSeriesMigrateEventView, self).get_context_data(**kwargs)
#         context['title'] = 'Migrate one StreamEventData point to the new model'
#         context['old_model'] = 'StreamEventData'
#         context['new_model'] = 'StreamTimeSeriesEvent'
#         return context


# class StaffStreamTimeSeriesEventDetailView(StaffRequiredMixin, DetailView):
#     model = StreamTimeSeriesEvent
#     template_name = 'staff/streamtimeseriesevent-detail.html'

#     def _add_timestamp_formats(self, *args):
#         for obj in args:
#             if obj is not None:
#                 obj_dt = obj.timestamp
#                 obj.timezone = obj_dt.tzinfo
#                 obj.raw_timestamp = obj_dt.timestamp()

#     def _prettify_extra_data(self, *args):
#         for obj in args:
#             if obj is not None:
#                 obj.extra_data = json.dumps(obj.extra_data, indent=2)

#     def get(self, request, *args, **kwargs):
#         self._streamevent_id = self.request.GET.get('event_ref')
#         return super(StaffStreamTimeSeriesEventDetailView, self).get(self, request, *args, **kwargs)

#     def get_context_data(self, *args, **kwargs):
#         context = super(StaffStreamTimeSeriesEventDetailView, self).get_context_data(*args, **kwargs)
#         timeseriesevent = self.get_object()
#         if self._streamevent_id:
#             streamevent = get_object_or_404(StreamEventData, pk=self._streamevent_id)
#         else:
#             streamevent = None
#         self._add_timestamp_formats(streamevent, timeseriesevent)
#         self._prettify_extra_data(streamevent, timeseriesevent)
#         # use int2vid to display block_id
#         timeseriesevent.block_vid = int2vid(timeseriesevent.block_id) if timeseriesevent.block_id else None
#         context['timeseriesevent'] = timeseriesevent
#         context['streamevent'] = streamevent
#         context['user_timezone'] = self.request.user.time_zone
#         return context
