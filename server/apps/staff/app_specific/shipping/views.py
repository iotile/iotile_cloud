import datetime
import logging
import secrets
import string

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView
from django.views.generic.edit import CreateView, FormView

from allauth.account.models import EmailAddress

from apps.org.models import Org
from apps.physicaldevice.claim_utils import device_claim
from apps.project.models import Project
from apps.projecttemplate.models import ProjectTemplate
from apps.staff.views import StaffRequiredMixin
from apps.streamer.worker.misc.adjust_timestamp import AdjustTimestampAction
from apps.utils.data_helpers.manager import DataManager
from apps.utils.iotile.variable import SYSTEM_VID, USER_VID
from apps.utils.timezone_utils import str_utc
from apps.verticals.shipping.utils.device_claim_helper import ShippingDeviceVerticalClaimHelper

from .forms import NewShippingOrgForm, NewShippingProjectForm, ShippingDeviceClaimForm, ShippingDeviceTimestampFixForm

logger = logging.getLogger(__name__)
user_model = get_user_model()

def generate_password():
    alphabet = string.ascii_letters + string.digits + '.' + '&'
    return ''.join(secrets.choice(alphabet) for i in range(15))


class StaffShippingView(StaffRequiredMixin, TemplateView):
    template_name = 'staff/shipping.html'

    def get_context_data(self, **kwargs):
        context = super(StaffShippingView, self).get_context_data(**kwargs)

        return context


class StaffNewShippingOrgView(StaffRequiredMixin, CreateView):
    model = Org
    form_class = NewShippingOrgForm
    template_name = 'staff/form.html'
    success_url = '/staff/shipping/'

    def form_valid(self, form):

        short_name = form.cleaned_data['short_name']
        short_name = slugify(short_name)
        owner = form.cleaned_data['owner']
        if owner == 'new':
            # 1.- create new Support Account
            email = 'help+{}@archsys.io'.format(short_name)
            username = 'support-{}'.format(short_name)
            password = generate_password()

            try:
                user = user_model.objects.create_user(email=email, username=username, password=password)
                user.name = 'Arch Support'
                user.is_active = True
                user.save()

                # Also set email as verified
                EmailAddress.objects.create(email=email, user=user, verified=True, primary=True)

                msg = '<h2 align="center">Support Email: {}<br>Support Password: {}<br>Make sure to save on LastPass</h2>'.format(email, password)
                messages.warning(self.request, msg)
            except Exception as e:
                messages.error(self.request, str(e))
                return HttpResponseRedirect(self.get_success_url())

        elif owner == 'user':
            user = self.request.user
        else:
            user = user_model.objects.get(slug=owner)

        self.object = form.save(commit=False)
        self.object.created_by = user
        self.object.save()

        self.object.register_user(user=user, is_admin=True, role='a0')

        # Finally, create required configAttributes
        helper = ShippingDeviceVerticalClaimHelper(None)
        helper.setup_org(self.object)

        msg = 'Organization "{}" created'.format(self.object.name)
        logger.info(msg)
        messages.success(self.request, msg)
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(StaffNewShippingOrgView, self).get_context_data(**kwargs)
        context['title'] = _('Create new Shipping Organization')
        return context


class StaffNewShippingProjectView(StaffRequiredMixin, CreateView):
    model = Project
    form_class = NewShippingProjectForm
    template_name = 'staff/form.html'
    success_url = '/staff/shipping/'

    def form_valid(self, form):

        # 1. Create project
        project_template = ProjectTemplate.objects.filter(name='Shipping Template').last()
        org = form.cleaned_data['org']
        self.object = form.save(commit=False)
        self.object.created_by = org.created_by
        self.object.org = org
        self.object.project_template = project_template
        self.object.save()

        # Create streamFilters and any other require object
        helper = ShippingDeviceVerticalClaimHelper(None)
        helper.setup_project(self.object)

        msg = 'Project "{}" created (with filters)'.format(self.object.name)
        logger.info(msg)
        messages.success(self.request, msg)
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(StaffNewShippingProjectView, self).get_context_data(**kwargs)
        context['title'] = _('New Shipping Project')
        return context


class StaffClaimShippingDeviceView(StaffRequiredMixin, FormView):
    template_name = 'staff/form.html'
    form_class = ShippingDeviceClaimForm

    def _check_shipping_device(self, device):

        if device.project:
            messages.error(self.request, 'Device is already claimed by another project')
            return False

        dt = device.template
        if not dt:
            messages.error(self.request, 'Device has no Device Template')
            return False

        if 'POD-1M' not in dt.external_sku:
            messages.error(self.request, 'Device is not a POD-1M')
            return False

        sg = device.sg

        if not sg:
            messages.error(self.request, 'Device has no Sensor Graph')
            return False

        if 'Shipping' not in sg.name:
            messages.error(self.request, 'Device requires a "Shipping" Sensor Graph')
            return False

        return True

    def form_valid(self, form):
        device = form.cleaned_data['device_id']
        project = form.cleaned_data['project']
        if device and project:

            if self._check_shipping_device(device):
                helper = ShippingDeviceVerticalClaimHelper(device)
                helper.adjust_device()
                device.save()

                device_claim(device=device, project=project, claimed_by=project.created_by)

                messages.success(self.request, 'Device {} has been claimed'.format(device.slug))
                return HttpResponseRedirect(reverse('staff:shipping'))

        return HttpResponseRedirect(reverse('staff:shipping'))

    def get_context_data(self, **kwargs):
        context = super(StaffClaimShippingDeviceView, self).get_context_data(**kwargs)
        context['title'] = _('Claim Shipping Device')
        return context


class StaffShippingDeviceTimestampFixView(StaffRequiredMixin, FormView):
    template_name = 'staff/form.html'
    form_class = ShippingDeviceTimestampFixForm

    def form_valid(self, form):
        device = form.cleaned_data['device_id']
        if device:

            # 1.- Get the Start/End Data records
            start_trip_stream_slug = str(device.get_stream_slug_for(SYSTEM_VID['TRIP_START']))
            end_trip_stream_slug = str(device.get_stream_slug_for(SYSTEM_VID['TRIP_END']))

            # Get Start/End records
            qs = DataManager.filter_qs(
                'data',
                stream_slug__in=[start_trip_stream_slug, end_trip_stream_slug]
            ).order_by('streamer_local_id', 'timestamp')

            start = end = None
            for data_item in qs:
                if data_item.stream_slug == start_trip_stream_slug:
                    start = data_item
                if data_item.stream_slug == end_trip_stream_slug:
                    end = data_item

            if start and end:

                # Do not rely on the Start Time being processed already, so get the timestamp
                # from its value
                base_ts = datetime.datetime.fromtimestamp(start.int_value, datetime.timezone.utc)
                base_ts = base_ts - datetime.timedelta(seconds=start.device_timestamp)

                # Schedule Data Fix
                payload = {
                    'user': self.request.user.slug,
                    'base_ts': str_utc(base_ts),
                    'device_slug': device.slug,
                    'start': start.streamer_local_id,
                    'end': end.streamer_local_id,
                    'type': 'data'
                }
                logger.info(payload)
                AdjustTimestampAction.schedule(payload)

                # Schedule Event Fix
                # For events, we need to get a different set of start/end seqids
                # To do so, we get the fist and last 5020 Data stream, and use the value which
                # points to the 5020 Event seqids
                shock_stream_slug = str(device.get_stream_slug_for(USER_VID['ACCEL']))
                shock_data_qs = DataManager.filter_qs(
                    'data',
                    stream_slug=shock_stream_slug,
                    streamer_local_id__gte=start.streamer_local_id,
                    streamer_local_id__lte=end.streamer_local_id
                ).order_by('streamer_local_id')
                first_shock = shock_data_qs.first()
                last_shock = shock_data_qs.last()
                if first_shock and last_shock:
                    payload['type'] = 'event'
                    payload['start'] = first_shock.int_value
                    payload['end'] = last_shock.int_value
                    logger.info(payload)
                    AdjustTimestampAction.schedule(payload)

                messages.success(self.request, 'Device {} has been scheduled for Timestamp Fixing'.format(device.slug))
            else:
                messages.error(self.request, 'Trip Start and/or End not found')

        return HttpResponseRedirect(reverse('staff:shipping'))

    def get_context_data(self, **kwargs):
        context = super(StaffShippingDeviceTimestampFixView, self).get_context_data(**kwargs)
        context['title'] = _('Shipping Device Data/Event Timestamp fixing')
        return context
