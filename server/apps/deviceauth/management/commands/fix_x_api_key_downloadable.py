import logging
import sys

from django.core.management.base import BaseCommand

from apps.deviceauth.models import DeviceKey

logger = logging.getLogger(__name__)


class Command(BaseCommand):

    def handle(self, *args, **options):
        DeviceKey.objects.filter(type='X-API-KEY').update(downloadable=True)
