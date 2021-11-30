from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, TemplateView

from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.s3file.views import S3FileUploadSignView, S3FileUploadSuccessEndpointView, S3FileUploadView
from apps.utils.objects.view_mixins import ByTargetAccessMixin

from .forms import StreamNoteForm
from .models import StreamNote


class StreamNoteListView(ByTargetAccessMixin, TemplateView):
    template_name = 'streamnote/list.html'

    def get_context_data(self, **kwargs):
        context = super(StreamNoteListView, self).get_context_data(**kwargs)

        target = self.get_target('can_read_notes')
        if isinstance(target, Project):
            project = target
        else:
            project = target.project

        if not target:
            raise Http404

        context['target'] = target
        context['project'] = project
        context['org'] = target.org
        context['notes'] = StreamNote.objects.user_note_qs(
            user=self.request.user, target_slug=self.kwargs['slug']
        ).select_related('created_by')

        if isinstance(target, Device):
            context['busy'] = target.busy
        else:
            context['busy'] = False
        return context


class StreamNoteCreateView(ByTargetAccessMixin, CreateView):
    model = StreamNote
    form_class = StreamNoteForm
    template_name = 'project/form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        target = self.get_target()
        self.object.target_slug = target.slug
        self.object.created_by = self.request.user
        self.object.timestamp = timezone.now()
        self.object.save()

        return HttpResponseRedirect(target.get_notes_url())

    def get_context_data(self, **kwargs):
        context = super(StreamNoteCreateView, self).get_context_data(**kwargs)
        target = self.get_target()
        if isinstance(target, Project):
            project = target
        else:
            project = target.project
        context['project'] = project
        context['org'] = target.org
        context['title'] = _('New Note')
        context['back_url'] = self.request.META.get('HTTP_REFERER')

        return context


class StreamNoteS3FileUploadView(S3FileUploadView):

    def get_allowed_extensions(self):
        return ['jpg', 'jpeg', 'png']

    def get_fineuploader_max_size(self):
        return settings.S3FILE_MAX_SIZE * 4

    def get_fineuploader_storage_dirname(self):
        path = super(StreamNoteS3FileUploadView, self).get_fineuploader_storage_dirname()
        return path + '/note'

    def get_fineuploader_success_endpoint(self):
        return reverse('streamnote:upload-success', kwargs={'pk': self.kwargs['pk']})

    def get_fineuploader_signature_endpoint(self):
        return reverse('streamnote:upload-sign', kwargs={'pk': self.kwargs['pk']})

    @method_decorator(login_required())
    def dispatch(self, *args, **kwargs):
        note = get_object_or_404(StreamNote, pk=self.kwargs['pk'])
        target = note.target
        if not target.org.has_permission(self.request.user, 'can_read_notes'):
            raise PermissionDenied("User has no access")
        return super(StreamNoteS3FileUploadView, self).dispatch(*args, **kwargs)


class StreamNoteS3FileUploadSuccessEndpointView(S3FileUploadSuccessEndpointView):
    note = None

    def post_s3file_save(self, s3file):
        self.note = get_object_or_404(StreamNote, pk=self.kwargs['pk'])
        self.note.attachment = s3file
        self.note.save()

    def get_response_data(self, s3file):
        if self.note:
            redirectURL = self.note.get_absolute_url()
        else:
            redirectURL = '/staff'

        response_data = {
            'redirectURL': redirectURL
        }
        return response_data


class StreamNoteS3FileUploadSignView(S3FileUploadSignView):
    private_key = settings.S3FILE_PRIVATE_KEY
    bucket_name = settings.S3FILE_BUCKET_NAME
    max_size = settings.S3FILE_MAX_SIZE * 4
