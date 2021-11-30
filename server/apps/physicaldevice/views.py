from django.core.exceptions import PermissionDenied
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _
from django.views.generic import RedirectView

from apps.ota.models import DeviceVersionAttribute
from apps.property.views import *
from apps.report.views import BaseGeneratedUserReportScheduleView
from apps.staff.views import FILTER_LOGS_LIMIT
from apps.streamer.models import StreamerReport
from apps.streamfilter.models import StreamFilter
from apps.utils.data_mask.mask_utils import clear_data_mask, set_data_mask
from apps.utils.timezone_utils import convert_to_utc
from apps.utils.views.basic import LoginRequiredAccessMixin
from apps.verticals.utils import get_device_detail_vertical_helper

from .claim_utils import *
from .data_utils import StreamDataCountHelper
from .forms import *
from .mixins import DeviceAccessMixin, DeviceCanResetAccessMixin, DeviceWriteAccessMixin
from .tasks import schedule_reset
from .worker.device_data_trim import DeviceDataTrimAction, get_streams_to_trim
from .worker.device_move import DeviceMoveAction

UPLOAD_EVENT_LIMIT = 100

logger = logging.getLogger(__name__)


class DeviceDetailView(DeviceAccessMixin, DetailView):
    model = Device
    template_name = 'device/detail.html'

    def _get_filter_list_for_device(self, streams):
        filters = {}
        for stream in streams:
            elements = stream.slug.split('--')
            filter_stream_key = '--'.join(['f', ] + elements[1:])
            try:
                # If 2 filters (project and device) are defined for one stream, take the filter of the device first
                filters[stream.slug] = {'filter': StreamFilter.objects.get(slug=filter_stream_key),
                                        'is_project_filter': False}
            except StreamFilter.DoesNotExist:
                # Check for project-wide filter
                filter_project_key = '--'.join(['f', elements[1], '', elements[3]])
                try:
                    filters[stream.slug] = {'filter': StreamFilter.objects.get(slug=filter_project_key),
                                            'is_project_filter': True}
                except StreamFilter.DoesNotExist:
                    pass
        return filters

    def get_context_data(self, **kwargs):
        context = super(DeviceDetailView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        context['api_key'] = getattr(settings, 'GOOGLE_API_KEY')

        streams = self.object.streamids.filter(
            enabled=True,
            block__isnull=True,
            project=self.object.project
        ).select_related('variable')

        streams.select_related('variable')
        context['stream_count'] = len(streams)

        context['data_counter'] = StreamDataCountHelper(self.object)

        # Get last streamer report upload (date & username of the uploader)
        context['last_streamerreport_update'] = StreamerReport.objects.filter(streamer__device=self.object).order_by('-sent_timestamp')[:UPLOAD_EVENT_LIMIT].first()

        # Get all archives but make sure only to include the ones for the current Org
        context['data_block_count'] = self.object.data_blocks.filter(org=self.object.org).count()

        filter_logs = []
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
        context['filters'] = self._get_filter_list_for_device(streams)

        context['generated_user_reports'] = GeneratedUserReport.objects.filter(
            source_ref=self.object.slug
        ).order_by('-created_on')

        # To show any application specific actions
        vertical_helper = get_device_detail_vertical_helper(self.object)
        context['vertical_action_menus'] = vertical_helper.action_menus(self.request.user)

        context['device_versions'] = DeviceVersionAttribute.objects.current_device_version_qs(self.object)

        return context


class DeviceListView(LoginRequiredAccessMixin, ListView):
    model = Device
    template_name = 'device/list.html'

    def get_queryset(self):
        project = Project.objects.get_from_request(self.request)
        return project.devices.all()

    def get_context_data(self, **kwargs):
        context = super(DeviceListView, self).get_context_data(**kwargs)
        return context


class DeviceUpdateView(DeviceWriteAccessMixin, UpdateView):
    model = Device
    form_class = DeviceForm
    template_name = 'org/form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(DeviceUpdateView, self).get_context_data(**kwargs)
        context['title'] = _('Edit IOTile Device')
        return context


class DevicePropertyView(DeviceAccessMixin, DetailView):
    model = Device
    template_name = 'device/property-detail.html'

    def get_context_data(self, **kwargs):
        context = super(DevicePropertyView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        context['properties'] = self.object.get_properties_qs()
        self.kwargs['target_slug'] = self.object.slug
        return context


class DeviceUploadEventsView(DeviceAccessMixin, DetailView):
    model = Device
    template_name = 'device/upload-events-detail.html'

    def get_context_data(self, **kwargs):
        context = super(DeviceUploadEventsView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        context['reports'] = StreamerReport.objects.filter(streamer__device=self.object).order_by('-sent_timestamp')[:UPLOAD_EVENT_LIMIT]
        return context


class DeviceMoveView(DeviceCanResetAccessMixin, UpdateView):
    model = Device
    form_class = DeviceMoveForm
    template_name = 'org/form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        dst_project = form.cleaned_data['dst_project']
        move_data = form.cleaned_data['move_data']

        # 1. Set Device as busy
        self.object.set_state('B0')
        self.object.save()

        args = {
            'user': self.request.user.slug,
            'device_slug': self.object.slug,
            'project_slug': dst_project.slug,
            'move_data': move_data
        }
        DeviceMoveAction.schedule(args=args)
        messages.info(
            self.request,
            'Task has been scheduled to move device {} to project {}. You will receive an email when it is done.'.format(
                self.object.slug,
                dst_project.slug
            ))

        device = Device.objects.get(id=self.object.id)
        return HttpResponseRedirect(device.get_absolute_url())

    def get_context_data(self, **kwargs):
        context = super(DeviceMoveView, self).get_context_data(**kwargs)
        context['title'] = _('Move IOTile Device')
        return context

    def get_form_kwargs(self):
        kwargs = super(DeviceMoveView, self).get_form_kwargs()
        project = self.object.project
        org = project.org
        kwargs['project_qs'] = Project.objects.user_project_qs(self.request.user)
        # Only allow move between projects in same org and make sure they move to another project
        kwargs['project_qs'] = kwargs['project_qs'].filter(org=org).exclude(id=project.id)
        return kwargs


class DeviceResetView(DeviceCanResetAccessMixin, UpdateView):
    model = Device
    form_class = DeviceResetForm
    template_name = 'project/form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)

        schedule_reset(self.object, self.request.user)
        messages.info(
            self.request,
            'Task has been scheduled to reset device {}. You will receive an email when it is done.'.format(
                self.object.slug
            )
        )

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(DeviceResetView, self).get_context_data(**kwargs)
        context['title'] = _('Reset/Clear Device Data')
        return context


class DeviceTrimView(DeviceCanResetAccessMixin, UpdateView):
    model = Device
    form_class = DeviceTrimForm
    template_name = 'project/utc_form.html'

    def form_valid(self, form):
        assert self.object.project
        org = self.object.project.org
        base_url = reverse('org:project:device:trim-confirm', kwargs={'org_slug': org.slug,
                                                                      'project_id': str(self.object.project.id),
                                                                      'pk': self.object.id})

        start_str = str_utc(form.cleaned_data['start']) if form.cleaned_data['start'] else None
        end_str = str_utc(form.cleaned_data['end']) if form.cleaned_data['end'] else None
        args = []
        if start_str:
            args.append('start={}'.format(start_str))
        if end_str:
            args.append('end={}'.format(end_str))
        confirm_url = '{base}?{args}'.format(base=base_url, args='&'.join(args))

        return HttpResponseRedirect(confirm_url)

    def get_context_data(self, **kwargs):
        context = super(DeviceTrimView, self).get_context_data(**kwargs)
        context['title'] = _('Trim Device Data')
        return context

    def get_form_kwargs(self):
        kwargs = super(DeviceTrimView, self).get_form_kwargs()
        kwargs['start'] = self.request.GET.get('start', None)
        kwargs['end'] = self.request.GET.get('end', None)
        return kwargs


class DeviceTrimByMaskView(DeviceCanResetAccessMixin, RedirectView, DetailView):
    def get_redirect_url(self, *args, **kwargs):
        device = get_object_or_404(Device, pk=kwargs['pk'])
        assert device.project
        org = device.project.org
        base_url = reverse('org:project:device:trim-confirm', kwargs={'org_slug': org.slug,
                                                                      'project_id': str(device.project.id),
                                                                      'pk': device.id})

        data_mask_range = get_data_mask_date_range(device)

        if data_mask_range is None:
            url = device.get_absolute_url()
            messages.add_message(self.request, messages.INFO, "Data is not masked, operation can't be performed.")
            return url

        start_str = end_str = None

        if 'start' in data_mask_range and data_mask_range['start'] is not None:
            start_str = str_utc(parse_datetime(data_mask_range['start']))
        if 'end' in data_mask_range and data_mask_range['end'] is not None:
            end_str = str_utc(parse_datetime(data_mask_range['end']))

        args = []
        if start_str:
            args.append('start={}'.format(start_str))
        if end_str:
            args.append('end={}'.format(end_str))
        confirm_url = '{base}?{args}'.format(base=base_url, args='&'.join(args))

        return confirm_url


class DeviceTrimConfirmView(DeviceCanResetAccessMixin, UpdateView):
    model = StreamId
    form_class = DeviceTrimConfirmForm
    template_name = 'device/trim-confirmation-form.html'

    def _get_date(self, type):
        '''
        :param type: 'start' or 'end'
        :return: datetime or None
        '''
        if type in self.request.GET and self.request.GET[type]:
            return parse_datetime(self.request.GET[type])
        else:
            return None

    def get_success_url(self):
        assert self.object.project
        org = self.object.project.org
        return reverse('org:project:device:detail', args=(org.slug, str(self.object.project.id), self.object.pk))

    def form_valid(self, form):
        self.object = form.save(commit=False)

        start = self._get_date('start')
        end = self._get_date('end')
        start_str = str_utc(start) if start else None
        end_str = str_utc(end) if end else None

        args = {
            'username': self.request.user.username,
            'device_slug': self.object.slug,
            'start': start_str,
            'end': end_str
        }
        DeviceDataTrimAction.schedule(args=args)
        messages.info(self.request,
                      'Task has been scheduled to data trim device {}. You will receive an email when it is done.'.format(
                          self.object.slug))

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(DeviceTrimConfirmView, self).get_context_data(**kwargs)

        context['start'] = self._get_date('start')
        context['end'] = self._get_date('end')

        # We don't want to delete system information that may be useful regardless of trimming,
        # For example, we want to keep the trip start and trip ended around even after the trim
        stream_qs = get_streams_to_trim(self.object)
        stream_slugs = [s.slug for s in stream_qs]

        if context['start']:
            data_qs = DataManager.filter_qs('data', stream_slug__in=stream_slugs, device_slug=self.object.slug)
            event_qs = DataManager.filter_qs('event', stream_slug__in=stream_slugs, device_slug=self.object.slug)

            logger.info('First Data: {}'.format(data_qs.order_by('timestamp').first()))
            data0_qs = data_qs.filter(timestamp__lt=context['start'])
            first_data = None
            if data0_qs.exists():
                context['data0_qs'] = data0_qs
                msg = '{0} data row(s) before {1} deleted'.format(data0_qs.count(), context['start'])
                logger.info(msg)
                first_data = data0_qs.first()
                context['oldest'] = convert_to_utc(first_data.timestamp)

            logger.info('First Event: {}'.format(event_qs.order_by('timestamp').first()))
            event0_qs = event_qs.filter(timestamp__lt=context['start'])
            if event0_qs.exists():
                context['event0_qs'] = event0_qs
                msg = '{0} event row(s) before {1} deleted'.format(event0_qs.count(), context['start'])
                logger.info(msg)
                older_event = event0_qs.first()
                if older_event and (not first_data or (older_event.timestamp < context['oldest'])):
                    context['oldest'] = older_event

        if context['end']:
            data_qs = DataManager.filter_qs('data', stream_slug__in=stream_slugs, device_slug=self.object.slug)
            event_qs = DataManager.filter_qs('event', stream_slug__in=stream_slugs, device_slug=self.object.slug)

            logger.info('Last Data: {}'.format(data_qs.order_by('timestamp').last()))
            data1_qs = data_qs.filter(timestamp__gt=context['end'])
            last_data = None
            if data1_qs.exists():
                context['data1_qs'] = data1_qs
                msg = '{0} data row(s) after {1} deleted'.format(data1_qs.count(), context['end'])
                logger.info(msg)
                last_data = data1_qs.last()
                context['newest'] = convert_to_utc(last_data.timestamp) if last_data else None

            logger.info('Last Event: {}'.format(event_qs.order_by('timestamp').last()))
            event1_qs = event_qs.filter(timestamp__gt=context['end'])
            if event1_qs.exists():
                context['event1_qs'] = event1_qs
                msg = '{0} event row(s) after {1} deleted'.format(event1_qs.count(), context['end'])
                logger.info(msg)
                newest_event = event1_qs.last()
                if newest_event and (not last_data or (newest_event.timestamp > context['newest'])):
                    context['newest'] = newest_event

        return context

    def get_form_kwargs(self):
        kwargs = super(DeviceTrimConfirmView, self).get_form_kwargs()
        kwargs['start'] = self.request.GET.get('start', None)
        kwargs['end'] = self.request.GET.get('end', None)
        return kwargs


class DeviceMaskView(DeviceCanResetAccessMixin, UpdateView):
    model = Device
    form_class = DeviceMaskForm
    template_name = 'project/utc_form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)

        start = form.cleaned_data.get('start', None)
        end = form.cleaned_data.get('end', None)
        if start or end:
            start_str = str_utc(start) if start else None
            end_str = str_utc(end) if end else None
            set_data_mask(self.object, start_str, end_str, [], [], user=self.request.user)
            messages.info(self.request, 'Device Mask Configuration Set {}'.format(self.object.slug))
        else:
            clear_data_mask(self.object, self.request.user)

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(DeviceMaskView, self).get_context_data(**kwargs)
        context['title'] = _('Mask Device Data')
        return context

    def get_form_kwargs(self):
        kwargs = super(DeviceMaskView, self).get_form_kwargs()
        kwargs['start'] = self.request.GET.get('start', None)
        kwargs['end'] = self.request.GET.get('end', None)
        kwargs['event_list'] = self.request.GET.get('events', None)
        kwargs['data_list'] = self.request.GET.get('data', None)
        return kwargs


class DeviceHealthStatusView(DeviceAccessMixin, DetailView):
    model = Device
    template_name = 'device/device-health-status.html'

    def get_context_data(self, **kwargs):
        context = super(DeviceHealthStatusView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        context['status'] = DeviceStatus.get_or_create(self.object)
        return context


class SeviceStatusSettingsView(DeviceWriteAccessMixin, UpdateView):
    model = DeviceStatus
    form_class = DeviceHealthForm
    template_name = 'project/form.html'

    def get_object(self, queryset=None):
        device = super(SeviceStatusSettingsView, self).get_object(queryset=queryset)
        if device:
            return device.get_or_create_status()

        raise PermissionDenied('User has no write permission to Device {}'.format(device.slug))

    def get_context_data(self, **kwargs):
        context = super(SeviceStatusSettingsView, self).get_context_data(**kwargs)
        org = self.object.device.org
        context.update(org.permissions(self.request.user))
        return context

    def get_form_kwargs(self):
        kwargs = super(SeviceStatusSettingsView, self).get_form_kwargs()
        org = self.object.device.org
        kwargs['org'] = org
        return kwargs

    def form_valid(self, form):
        self.object = form.save(commit=False)
        recipients = form.cleaned_data['recipients']
        self.object.notification_recipients = recipients
        extras = form.cleaned_data['extras']
        extra_emails = extras.split('\n')
        for extra_email in extra_emails:
            extra_email = extra_email.strip()
            if extra_email:
                self.object.notification_recipients.append('email:{}'.format(extra_email))
        self.object.save()
        return HttpResponseRedirect(self.object.get_absolute_url())


class DeviceFilterLogsClearView(DeviceAccessMixin, UpdateView):
    model = Device
    form_class = DeviceFilterLogsClearForm
    template_name = 'project/form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        for stream in self.object.streamids.all():
            try:
                qs = DynamoFilterLogModel.target_index.query(stream.slug)
                with DynamoFilterLogModel.batch_write() as batch:
                    for item in qs:
                        batch.delete(item)
            except Exception:
                pass

        return HttpResponseRedirect(self.object.get_absolute_url())


class DeviceGeneratedUserReportScheduleView(BaseGeneratedUserReportScheduleView):
    template_name = "project/form.html"

    def get_source_ref_object(self):
        return get_object_or_404(Device, pk=self.kwargs['pk'])
