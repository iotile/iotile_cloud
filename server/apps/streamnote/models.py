from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

# Create your models here.
from apps.s3file.models import S3File
from apps.utils.objects.utils import get_object_by_slug

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')


def get_note_target_by_slug(target_slug):
    target = None
    elements = target_slug.split('--')
    if len(elements) > 1 and elements[0] in ['s', 'd', 'b', 'p']:
        name, target = get_object_by_slug(target_slug)

    return target


class StreamNoteManager(models.Manager):
    """
    Manager to help with Device Management
    """

    def user_note_qs(self, user, target_slug=None):
        if target_slug:
            target = get_note_target_by_slug(target_slug)

            if target and target.has_access(user):
                return self.model.objects.filter(target_slug=target_slug)
            else:
                return self.model.objects.none()
        else:
            return self.model.objects.filter(created_by=user)

    def object_notes_qs(self, obj, type=None):
        slug = obj.slug
        if type == None:
            return self.model.objects.filter(target_slug=slug)
        return self.model.objects.filter(target_slug=slug, type=type)


class StreamNote(models.Model):

    # First char is note type: "s" for system, "f" for filter, "u" for user
    # Second char if level: "c" for critical, "i" for info
    TYPE_CHOICES = (
        ('sc', 'System generated (Critical)'),
        ('si', 'System generated (Info)'),
        ('fi', 'Filter generated'),
        ('ui', 'User Note'),
    )

    type = models.CharField(max_length=2, default='ui', choices=TYPE_CHOICES, blank=True)

    target_slug = models.CharField(max_length=39, default='', null=True)

    # Absolute timestamp computed by the gateway and/or server (in UTC)
    timestamp = models.DateTimeField(null=True, blank=True)

    note = models.TextField(null=True, blank=True)

    attachment = models.OneToOneField(S3File, on_delete=models.CASCADE, blank=True, null=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    objects = StreamNoteManager()

    class Meta:
        ordering = ['target_slug', 'timestamp']
        verbose_name = _("Stream Note")
        verbose_name_plural = _("Stream Notes")

    def __str__(self):
        return '{0} on {1}'.format(self.target_slug, self.timestamp)

    @property
    def target(self):
        return get_note_target_by_slug(self.target_slug)

    def get_absolute_url(self):
        return reverse('streamnote:list', args=(self.target_slug,))

    def get_upload_url(self):
        return reverse('streamnote:upload', args=(self.id,))

    def get_attachment_url(self):
        if self.attachment:
            return self.attachment.get_absolute_url()
        return self.get_absolute_url()

    def get_type_icon(self):
        factory = {
            'sc': 'fa-exclamation-triangle',
            'si': 'fa-info-circle',
            'fi': 'fa-info',
            'ui': 'fa-comment'
        }
        if self.type in factory:
            return factory[self.type]
        return ''

