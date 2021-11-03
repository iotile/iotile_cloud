import uuid
import logging
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.db.models import Manager

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
logger = logging.getLogger(__name__)


class WorkerStatistics(models.Model):

    SPAN_CHOICES = (("d", "Day"),
                    ("w", "Week"),
                    ("m", "Month"))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # stats collected based on logs from (timestamp - span) to timestamp
    timestamp = models.DateTimeField(null=True, blank=True)
    span = models.CharField(max_length=1, choices=SPAN_CHOICES)

    task_name = models.CharField(max_length=100, unique=False)
    total_count = models.IntegerField(blank=True, null=True)
    error_count = models.IntegerField(blank=True, null=True)
    total_execution_time = models.FloatField(blank=True, null=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)

    class Meta:
        ordering = ['timestamp', 'task_name']
        verbose_name = _("Worker Statistics")
        verbose_name_plural = _("Worker Statistics")

    def __str__(self):
        return '{0} at {1}, span {2}, total count {3}'.format(self.task_name, self.timestamp.isoformat(), self.span, self.total_count)

    @property
    def average_execution_time(self):
        if self.total_count:
            return self.total_execution_time / self.total_count
        return 0.0
