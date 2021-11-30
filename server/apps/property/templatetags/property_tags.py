import logging

from django import template

from apps.property.models import GenericProperty

register = template.Library()
logger = logging.getLogger(__name__)


@register.filter
def properties(obj):
    qs = GenericProperty.objects.object_properties_qs(obj)
    return qs

