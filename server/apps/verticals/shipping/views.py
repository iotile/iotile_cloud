import json
import logging

import boto3
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.html import format_html
from django.views.generic import DetailView, FormView, UpdateView

from apps.configattribute.models import ConfigAttribute
from apps.project.mixins import get_project_menu_extras
from apps.project.models import Project
from apps.verticals.mixins import VerticalProjectAccessMixin, VerticalDeviceAccessMixin
from apps.s3file.views import S3FileUploadSuccessEndpointView, S3FileUploadView, S3FileUploadSignView
from apps.property.models import GenericProperty
from apps.s3file.views import S3FileUploadSuccessEndpointView, S3FileUploadView
from apps.streamfilter.models import StreamFilter
from apps.streamnote.models import StreamNote
from apps.streamer.models import Streamer
from apps.utils.aws.common import AWS_REGION
from apps.utils.aws.sns import sns_lambda_message, sns_staff_notification
from apps.verticals.mixins import VerticalDeviceAccessMixin, VerticalProjectAccessMixin

from .forms import *
from .utils.project_status_report import TripProjectStatusReport
from .utils.trip import set_device_to_active

SNS_UPLOAD_SXD = getattr(settings, 'SNS_UPLOAD_SXD')

logger = logging.getLogger(__name__)


class ShippingProjectView(VerticalProjectAccessMixin, DetailView):
    """This view can be accessed stand-alone but is also available on the default Project View (for shipping projects)"""
    model = Project
    page = None

    def get_template_names(self):

        # No longer support widget pages, so just assume default page
        return 'shipping/project-status.html'

    def get_context_data(self, **kwargs):
        context = super(ShippingProjectView, self).get_context_data(**kwargs)

        context.update(self.get_basic_context(self.object))

        summary = TripProjectStatusReport(self.object)
        summary.analyze()
        context['config'] = summary.config
        context['results'] = summary.results
        context['device_count'] = summary.device_count
        context['active_count'] = summary.active_count
        context['ended_count'] = summary.ended_count
        context['api_key'] = getattr(settings, 'GOOGLE_API_KEY')
        context['is_staff'] = self.request.user.is_staff
        context['filters'] = StreamFilter.objects.filter(project=self.object)
        context['webapp'] = self.object.get_webapp_url()

        return context


class SxdDeviceFormView(VerticalProjectAccessMixin, FormView):
    template_name = 'shipping/sxd_flow.html'
    form_class = SxdDeviceForm
    _project = None

    def form_valid(self, form):
        d = form.cleaned_data['external_id']
        if not d:
            messages.error(self.request, 'No device found')
            return reverse('apps-shipping:sxd-step-device', kwargs={'slug': self.kwargs['slug']})

        # Reset device data ID to load a trip in the past
        if form.cleaned_data['reset']:
            streamer = Streamer.objects.filter(device=d.id).update(last_id=0)

        return HttpResponseRedirect(reverse('apps-shipping:sxd-step-properties', kwargs={'slug': d.slug}))

    def get_form_kwargs(self):
        kwargs = super(SxdDeviceFormView, self).get_form_kwargs()
        self._project = get_object_or_404(Project, slug=self.kwargs['slug'])
        kwargs['project'] = self._project
        return kwargs

    def get_context_data(self, **kwargs):
        context = super(SxdDeviceFormView, self).get_context_data(**kwargs)

        assert(self._project)
        context.update(self.get_basic_context(self._project))

        context['production'] = settings.PRODUCTION
        context['step'] = 1

        return context


class SxdPropertyFormView(VerticalDeviceAccessMixin, UpdateView):
    model = Device
    template_name = 'shipping/sxd_flow.html'
    form_class = SxdPropertiesForm

    def form_valid(self, form):
        for name in form.cleaned_data.keys():
            value = form.cleaned_data[name]
            if isinstance(value, GenericPropertyOrgEnum):
                value = value.value
            if value:
                try:
                    gp = GenericProperty.objects.get(
                        target=self.object.slug,
                        name=name
                    )
                    gp.set_str_value(value)
                    gp.creayed_by = self.request.user
                    gp.save()
                except GenericProperty.DoesNotExist:
                    GenericProperty.objects.create_str_property(
                        slug=self.object.slug,
                        name=name,
                        value=value,
                        created_by=self.request.user
                    )

        return HttpResponseRedirect(reverse('apps-shipping:sxd-step-upload', kwargs={'slug': self.object.slug}))

    def get_context_data(self, **kwargs):
        context = super(SxdPropertyFormView, self).get_context_data(**kwargs)

        context['production'] = settings.PRODUCTION
        context['step'] = 2
        context['device'] = self.object
        project = context['device'].project
        if project:
            if project.org:
                context['project'] = project
                context['org'] = project.org
                context.update(project.org.permissions(self.request.user))
                context['project_menu_extras'] = get_project_menu_extras(project)

        return context


class ShippingSxdFileUploadView(VerticalDeviceAccessMixin, S3FileUploadView):

    def get_allowed_extensions(self):
        return ['sxd', ]

    def get_fineuploader_max_size(self):
        return settings.S3FILE_MAX_SIZE * 16 # 64MB

    def get_fineuploader_storage_dirname(self):
        path = super(ShippingSxdFileUploadView, self).get_fineuploader_storage_dirname()
        return path + '/sxd/{}'.format(self.kwargs['slug'])

    def get_fineuploader_success_endpoint(self):
        return reverse('apps-shipping:sxd-step-upload-success', kwargs={'slug': self.kwargs['slug']})

    def get_fineuploader_signature_endpoint(self):
        return reverse('apps-shipping:sxd-step-sign', kwargs={'slug': self.kwargs['slug']})

    def get_context_data(self, **kwargs):
        context = super(ShippingSxdFileUploadView, self).get_context_data(**kwargs)
        context['title'] = format_html("""
        <h1>Step 3 - SXd File Uploader</h1>
        <h2>After review, the data will be uploaded by arch</h2>
        <p></p>
        """)

        context['user'] = self.request.user

        return context


class ShippingSxdFileUploadSuccessEndpointView(S3FileUploadSuccessEndpointView):

    def post_s3file_save(self, s3file):
        logger.info('SXD File saved: {}'.format(s3file))
        slug = self.kwargs['slug']
        device = get_object_or_404(Device, slug=slug)

        # Create a StreamNote logging the upload
        note = StreamNote.objects.create(
            target_slug=device.slug,
            timestamp=s3file.created_on,
            note='An SXd file was successfully uploaded for processing\nFile: {}'.format(s3file.key),
            created_by=self.request.user,
            type='si'
        )

        msg = note.note
        msg += '\nDevice Page: {}{}'.format(settings.DOMAIN_BASE_URL, device.get_absolute_url())
        msg += '\nUploaded by {}'.format(self.request.user)
        msg += '\nSent to {}'.format(SNS_UPLOAD_SXD)
        sns_staff_notification(msg)

        # Send a SNS message to trigger lambda function
        msg = {
            'device_slug': slug,
            'uuid': str(s3file.id),
            'title': s3file.title,
            'bucket': s3file.bucket,
            'key': s3file.key,
            'user': self.request.user.username,
            'token': self.request.user.jwt_token,
        }
        sns_lambda_message(SNS_UPLOAD_SXD, msg)

        # Notify user of submission
        msg = 'Your SXd file has been submitted for processing. Contact help@archsys.io for support'
        messages.info(self.request, msg)

    def get_response_data(self, s3file):
        slug = self.kwargs['slug']
        device = get_object_or_404(Device, slug=slug)
        redirectURL = device.get_absolute_url()

        response_data = {
            'redirectURL': redirectURL
        }
        return response_data


class ShippingSxdFileUploadSignView(S3FileUploadSignView):
    private_key = settings.S3FILE_PRIVATE_KEY
    bucket_name = settings.S3FILE_BUCKET_NAME
    max_size = settings.S3FILE_MAX_SIZE * 16


class DeviceStartTripView(VerticalDeviceAccessMixin, UpdateView):
    model = Device
    template_name = 'shipping/start-trip.html'
    form_class = DeviceStartTripForm

    def form_valid(self, form):
        for name in form.cleaned_data.keys():
            value = form.cleaned_data[name]
            if isinstance(value, GenericPropertyOrgEnum):
                value = value.value
            if value:
                try:
                    gp = GenericProperty.objects.get(
                        target=self.object.slug,
                        name=name
                    )
                    gp.set_str_value(value)
                    gp.creayed_by = self.request.user
                    gp.save()
                except GenericProperty.DoesNotExist:
                    GenericProperty.objects.create_str_property(
                        slug=self.object.slug,
                        name=name,
                        value=value,
                        created_by=self.request.user
                    )

        set_device_to_active(self.object, self.request.user)

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(DeviceStartTripView, self).get_context_data(**kwargs)
        context['production'] = settings.PRODUCTION
        context['device'] = self.object
        project = context['device'].project
        if project:
            if project.org:
                context['project'] = project
                context['org'] = project.org
                context.update(project.org.permissions(self.request.user))
                context['project_menu_extras'] = get_project_menu_extras(project)

        return context
