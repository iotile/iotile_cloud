import logging
import sys

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.ota.models import DeviceVersionAttribute
from apps.physicaldevice.models import Device
from apps.sensorgraph.models import SensorGraph

logger = logging.getLogger(__name__)

DEFAULT_OS_VERSION = {
    'tag': 1024,
    'major': 0,
    'minor': 0
}

DEFAULT_APP_VERSION = {
    'tag_by_sg': [
        'Water Meter'
    ],
    'major': 0,
    'minor': 0
}

class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', dest='force', default=False,
                            help='Create new versions without checking if they exist')

    def handle(self, *args, **options):
        versions = DeviceVersionAttribute.objects.all().select_related('device')
        existing_versions = {
            'os': {},
            'sg': {}
        }
        for version in versions:
            slug = version.device.slug
            if slug not in existing_versions[version.type]:
                existing_versions[version.type][slug] = version
            else:
                if version.updated_ts > existing_versions[slug].updated_ts:
                    existing_versions[version.type][slug] = version
        for device in Device.objects.all():
            if device.slug not in existing_versions['os']:
                ver = DeviceVersionAttribute.objects.create(
                    device=device,
                    type='os',
                    tag=DEFAULT_OS_VERSION['tag'],
                    major_version=DEFAULT_OS_VERSION['major'],
                    minor_version=DEFAULT_OS_VERSION['minor'],
                    streamer_local_id=1,
                    updated_ts=timezone.now()
                )
                print('New Device Version {0}: {1}'.format(device.slug, ver.version))

        for name in DEFAULT_APP_VERSION['tag_by_sg']:
            sg_qs = SensorGraph.objects.filter(name=name)
            for sg in sg_qs:
                for device in sg.devices.all():
                    if device.slug not in existing_versions['sg']:
                        ver = DeviceVersionAttribute.objects.create(
                            device=device,
                            type='sg',
                            tag=sg.app_tag,
                            major_version=0,
                            minor_version=0,
                            streamer_local_id=1,
                            updated_ts=timezone.now()
                        )
                        print('New Device Version {0}: {1}'.format(device.slug, ver.version))





