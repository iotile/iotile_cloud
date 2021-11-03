import uuid
import logging
import datetime
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.template.defaultfilters import slugify
from django.contrib.postgres.fields import ArrayField

from apps.org.models import Org
from apps.project.models import Project
from apps.s3file.models import S3File
from apps.emailutil.tasks import Email

from .generator.config import rpt_configuration_requirements_met

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
logger = logging.getLogger(__name__)


class UserReport(models.Model):
    PERIOD_CHOICES = (('x', 'No (Manual only)'),
                      ('d', 'Run daily'),
                      ('w', 'Run weekly (on Sundays)'),
                      ('m', 'Run monthly (end of month)'))

    FORMAT_CHOICES = (
        ('default', 'General - Default'),
        ('end_of_trip', 'Shipping - End of Trip'),
        ('analytics', 'Shipping - Analytics'),
    )

    label = models.CharField(max_length=50)

    # {
    #    'cols': [{
    #      'name': 'Water Usage',
    #      'vars': [
    #         {'lid': '5001', 'name': 'IO 1'},
    #         {'lid': 'foo', 'name': 'IO 2'}
    #      ],
    #      'type': 'water-meter-volume',
    #      'units': 'out--water-meter-volume--acre-feet',
    #      'aggregate': 'sum/max/min'
    #     }]
    # }
    config = models.JSONField(null=True, blank=True)

    # List of supported slugs: Project, Device and/or StreamId
    # e.g. "p--0001", "d--0002", "s--0000-0001--0000-0000-0000-0002--501"
    sources = ArrayField(models.CharField(max_length=42), blank=True, default = list)

    generator = models.CharField('Report template', max_length=15,
                                 choices=FORMAT_CHOICES, default='default')
    interval = models.CharField(max_length=2, choices=PERIOD_CHOICES, default='x')

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='reports')

    notification_recipients = ArrayField(models.CharField(max_length=64), blank=True, default = list)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['org', 'label']
        verbose_name = _('User Report')
        verbose_name_plural = _('User Reports')

    def save(self, *args, **kwargs):
        if not self.config:
            self.config = {
                'cols': []
            }
        super(UserReport, self).save(*args, **kwargs)

    def __str__(self):
        return '{0}'.format(self.label)

    def get_add_project_url(self):
        return reverse('org:report:add-project', args=(self.org.slug, self.id))

    def get_configure_url(self):
        return '/org/{}/report/{}/{}/configure/'.format(self.org.slug, self.id, self.generator)

    def get_generate_url(self):
        return '/org/{}/report/{}/{}/generate/'.format(self.org.slug, self.id, self.generator)

    def get_item_extra_snippet_path(self):
        return 'report/{0}/report_item_extra_snippet.html'.format(self.generator)

    def has_access(self, user):
        if user.is_staff:
            return True

        if self.org:
            return self.org.has_access(user)

        return self.created_by == user

    def get_period_for_interval(self, end=None):
        if self.interval == 'x':
            return None, None

        factory = {
            'd': lambda a: a - datetime.timedelta(days=1),
            'w': lambda a: a - datetime.timedelta(days=7),
            'm': lambda a: a - datetime.timedelta(days=30)
        }

        end = end if end else timezone.now()
        start = factory[self.interval](end)

        return start, end

    def fully_configured(self):
        # All required fields have been entered, and the report is ready to be generated
        return self.notification_recipients and \
               rpt_configuration_requirements_met(
                   generator=self.generator, config=self.config, sources=self.sources
               )


class GeneratedUserReport(models.Model):
    """
    Model represents a generated Report File, stored on S3 as a static file (or set of files)

    """

    STATUS_CHOICES = (

        ('GS', 'Scheduled...'),
        ('G0', 'Generating...'),
        ('G1', 'Report Generation Completed'),
        ('GE', 'Generation Failure'),
    )

    # We need a UUID as a primary ID as that is used to mkae the link hard to find
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    label = models.CharField(max_length=50)

    # Reports are generated based on a UserReport object, but that object may be deleted after
    # generation, so the field is not required
    report = models.ForeignKey(UserReport, on_delete=models.SET_NULL,
                               blank=True, null=True, related_name='generated_reports')

    # All generated reports belong to one and only one Organization
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='generated_reports')

    # public = models.BooleanField(default=False)
    # notes = models.TextField(null=True, blank=True)

    # Reports are generated from a given reference, usually a Device or a DataBlock
    # But the reference could also be a Project
    source_ref = models.CharField(max_length=39, default='', null=True)

    # This is the top level file, usually index.html
    index_file = models.OneToOneField(S3File, on_delete=models.CASCADE, blank=True, null=True)

    # The state of the device. e.g. Busy when an archive or reset was scheduled
    status = models.CharField(_('Status'), max_length=2, choices=STATUS_CHOICES, default='G0', blank=True)

    public = models.BooleanField(default=False)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['org', 'created_on', 'label']
        verbose_name = _('Generated Report')
        verbose_name_plural = _('Generated Reports')

    def save(self, *args, **kwargs):
        super(GeneratedUserReport, self).save(*args, **kwargs)

    def __str__(self):
        return '{0}'.format(self.label)

    def has_access(self, user):
        if user.is_staff:
            return True

        if self.org:
            return self.org.has_permission(user, 'can_access_reports')

        return self.created_by == user

    def set_or_create_s3file(self, basename, user):
        key_template = getattr(settings, 'REPORTS_S3FILE_KEY_FORMAT')
        key_name = key_template.format(org=self.org.slug, uuid=str(self.id), base=basename)

        s3file = S3File.objects.set_or_create_file(
            uuid=self.id,
            name=self.label,
            bucket=getattr(settings, 'REPORTS_S3FILE_BUCKET_NAME'),
            key=key_name,
            user=user
        )
        return s3file

    def get_link(self):
        if self.index_file:
            return self.index_file.url
        return ''

    def get_absolute_url(self):
        return reverse('org:report:generated-detail', args=(str(self.org.slug), str(self.id),))

    def get_edit_url(self):
        return reverse('org:report:generated-edit', args=(str(self.org.slug), str(self.id),))

    def get_delete_url(self):
        return reverse('org:report:generated-delete', args=(str(self.org.slug), str(self.id),))

    def get_public_url(self):
        return reverse('public-report', args=(str(self.id),))

    def get_full_public_url(self):
        return '{0}{1}'.format(settings.DOMAIN_BASE_URL, self.get_public_url())

    def send_notifications(self):
        subject = _('IOTile Cloud Analytics Report: {}'.format(self.label))

        domain = getattr(settings, 'DOMAIN_BASE_URL')
        ctx = {
            'url': '{0}{1}'.format(domain, self.get_absolute_url()),
            'label': self.label,
            'source_ref': self.source_ref
        }

        user_email = Email()
        user_email.send_email(
            label='report/generated_report_done',
            subject=subject,
            ctx=ctx,
            emails=[self.created_by.email,]
        )






