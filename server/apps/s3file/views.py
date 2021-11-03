import logging
import json
import uuid
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.views.generic import DetailView, CreateView, TemplateView
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from django.utils.html import format_html

from apps.utils.fineuploader.sign import FineUploaderSignMixIn
from apps.utils.views.basic import LoginRequiredAccessMixin

from .models import *

logger = logging.getLogger(__name__)


class S3FileDetailView(LoginRequiredAccessMixin, DetailView):
    model = S3File
    template_name = 's3file/detail.html'

    def get_context_data(self, **kwargs):
        context = super(S3FileDetailView, self).get_context_data(**kwargs)
        return context


class S3FileUploadView(LoginRequiredAccessMixin, TemplateView):
    template_name = 's3file/file-uploader.html'
    fineuploader_item_limit = 1
    s3_acl = 'private'

    def get_allowed_extensions(self):
        return ['trub', 'zip', 'json']

    def get_fineuploader_max_size(self):
        return settings.S3FILE_MAX_SIZE

    def get_fineuploader_storage_dirname(self):
        return settings.S3FILE_INCOMING_KEYPATH

    def get_fineuploader_success_endpoint(self):
        return reverse('s3file:upload-success')

    def get_fineuploader_signature_endpoint(self):
        return reverse('s3file:upload-signee')

    def get_context_data(self, **kwargs):
        context = super(S3FileUploadView, self).get_context_data(**kwargs)

        context['fineuploader_request_endpoint'] = settings.S3FILE_ENDPOINT.rstrip('/')
        context['fineuploader_accesskey'] = settings.S3FILE_PUBLIC_KEY
        context['fineuploader_success_endpoint'] = self.get_fineuploader_success_endpoint()
        context['fineuploader_signature_endpoint'] = self.get_fineuploader_signature_endpoint()
        context['fineuploader_max_size'] = self.get_fineuploader_max_size()
        context['fineuploader_item_limit'] = self.fineuploader_item_limit
        context['fileuploader_allowed_extensions'] = self.get_allowed_extensions()
        context['s3_acl'] = self.s3_acl
        context['title'] = format_html('<h1>File Uploader</h1>')

        # The actual UUID will be generated by fineuploader so ignore now
        context['fineuploader_storage_dirname'] = self.get_fineuploader_storage_dirname()

        return context


# Create your views here.
class S3FileUploadSuccessEndpointView(View):
    http_method_names = ['post',]

    def post_s3file_save(self, s3file):
        pass

    def get_response_data(self, s3file):
        response_data =  {
            'redirectURL': s3file.get_absolute_url()
        }
        return response_data

    def post(self, request, *args, **kwargs):
        """ This is where the upload will send a POST request after the
        file has been stored in S3.
        """
        # Note that Fine Uploader will still send the bucket, key, filename, UUID, and etag (if available) as well
        #print('success_redirect GET: ' + str(self.request.POST))

        response = HttpResponse()
        if not (self.request.POST.get(u'name') and self.request.POST.get(u'key') and self.request.POST.get(u'uuid')):
            response.status_code = 405
            return response

        name = self.request.POST.get(u'name')
        key = self.request.POST.get(u'key')
        file_uuid = self.request.POST.get(u'uuid')

        # DO SOMETHING
        logger.info('Uploaded file successfully: name={0}, key={1}, uuid={2}'.format(name,
                                                                                     key,
                                                                                     file_uuid))

        real_uuid = uuid.UUID(file_uuid)
        s3file = S3File.objects.create_file(uuid=real_uuid, name=name, key=key, user=request.user)

        self.post_s3file_save(s3file)

        response.status_code = 200
        response['Content-Type'] = "application/json"
        response_data =  self.get_response_data(s3file)
        response.content = json.dumps(response_data)

        return response

    @method_decorator(login_required)
    @csrf_exempt
    def dispatch(self, request, *args, **kwargs):
        return super(S3FileUploadSuccessEndpointView, self).dispatch(request, *args, **kwargs)


class S3FileUploadSignView(FineUploaderSignMixIn, View):
    private_key = settings.S3FILE_PRIVATE_KEY
    bucket_name = settings.S3FILE_BUCKET_NAME
    max_size = settings.S3FILE_MAX_SIZE

