import logging
from django import template

from apps.streamnote.models import StreamNote

register = template.Library()
logger = logging.getLogger(__name__)


@register.filter
def notes(obj):
    qs = StreamNote.objects.object_notes_qs(obj)
    return qs

