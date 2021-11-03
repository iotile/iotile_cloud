import logging
import os
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.template.defaultfilters import slugify

from apps.utils.gid.convert import int16gid

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
logger = logging.getLogger(__name__)

class PageTemplate(models.Model):
    """
    Views are currently global.
    TODO: add a way to assign Pages to Projects for customization
    """

    TYPE_CHOICES = (
        ('DEFA', 'Default Template'),
        ('BLUR', 'Blur Template'),
        ('IONIC', 'Ionic App'),
    )

    slug = models.SlugField(max_length=82, default='', unique=True)
    label = models.CharField(max_length=60, unique=True)
    type = models.CharField(max_length=5, choices=TYPE_CHOICES, default='DEFA')
    template_path = models.CharField(max_length=60)

    include_device_status = models.BooleanField(default=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    dashboard_extra = models.JSONField(null=True, blank=True)
    mobile_extra = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['slug']
        verbose_name = _('Page Template')
        verbose_name_plural = _('Page Templates')

    def __str__(self):
        return '{0}'.format(self.label)

    def save(self, *args, **kwargs):
        self.slug = slugify(self.label)
        super(PageTemplate, self).save(*args, **kwargs)

    def get_html_template(self):
        return os.path.join(self.template_path, 'page.html')


class WidgetTemplate(models.Model):

    TYPE_CHOICES = (
        ('SERIES', 'Time Series'),
        ('LAST', 'Last value'),
        ('COUNT', 'Count entries'),
        ('SUM', 'Accumulate'),
        ('AVG', 'Average'),
        ('MAXMIN', 'Max/Min'),
        ('STATS', 'Data Stats'),
    )

    template_path = models.CharField(max_length=60)
    label = models.CharField(_('Label'), max_length=60, default='', blank=True)

    data_type = models.CharField(max_length=8, choices=TYPE_CHOICES, default='SERIES')

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['label']
        verbose_name = _('Widget Template')
        verbose_name_plural = _('Widget Templates')

    def __str__(self):
        return '{0}'.format(self.label)

    def get_html_template(self):
        return os.path.join(self.template_path, 'widget.html')

    def get_js_template(self):
        return os.path.join(self.template_path, 'script.js')


class WidgetInstance(models.Model):

    widget_definition = models.ForeignKey(WidgetTemplate, on_delete=models.CASCADE, related_name='widgets')
    page_definition = models.ForeignKey(PageTemplate, on_delete=models.CASCADE, related_name='widgets')
    label = models.CharField(_('Label'), max_length=60, default='', blank=True)
    primary_lid = models.IntegerField(_('Primary Variable ID'), default=0, blank=True)

    mobile_extra = models.JSONField(null=True, blank=True)
    desktop_extra = models.JSONField(null=True, blank=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['id']
        verbose_name = _('Widget Instance')
        verbose_name_plural = _('Widget Instances')

    def __str__(self):
        return '{0}'.format(self.label)

    @property
    def primary_variable_id_in_hex(self):
        return int16gid(self.primary_lid)

