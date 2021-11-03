import sys
import logging
from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.template.defaultfilters import slugify

from apps.org.models import Org
from apps.project.models import Project
from apps.devicetemplate.models import DeviceTemplate
from apps.sensorgraph.models import SensorGraph
from apps.physicaldevice.models import Device
from apps.physicaldevice.claim_utils import device_claim

logger = logging.getLogger(__name__)

class Command(BaseCommand):

    _org_name = 'Arch - Internal'
    _project_names = [
        'Mobile App Testing Project - Soil',
        'Mobile App Testing Project - Water'
    ]
    _projects = []
    _device_info = [
        {
            'id': 3,
            'label': 'Double Soil Moisture',
            'device_template':'pod-1gg1-v3-0-0',
            'sg': 'double-soil-moisture-v2-0-0',
            'project': 0
        },
        {
            'id': 4,
            'label': 'Single Soil Moisture',
            'device_template': 'pod-1gg1-v3-0-0',
            'sg': 'single-soil-moisture-v2-0-0',
            'project': 0
        },
        {
            'id': 5,
            'label': 'ES1 Prod Firmware, Robust Reports',
            'device_template': 'pod-1gg1-v3-0-0',
            'sg': 'water-meter-v1-1-0',
            'project': 1
        },
        {
            'id': 6,
            'label': 'POD1 Robust Reports',
            'device_template': 'pod-1gg1-v3-0-0',
            'sg': 'water-meter-v1-1-0',
            'project': 1
        },
        {
            'id': 7,
            'label': 'POD1 Old Reports',
            'device_template': 'pod-1gg1-v3-0-0',
            'sg': 'water-meter-v1-1-0',
            'project': 1
        },
        {
            'id': 8,
            'label': 'POD1 (Someone Always Connected)',
            'device_template': 'pod-1gg1-v3-0-0',
            'sg': 'water-meter-v1-1-0',
            'project': 1
        }
    ]

    def _add_karma_test_projects(self, admin):
        org_slug = slugify(self._org_name)
        try:
            org = Org.objects.get(slug=org_slug)
        except Org.DoesNotExist:
            org = Org.objects.create_org(name=self._org_name, created_by=admin)
            print('Created Org: {}'.format(org))

        for pname in self._project_names:
            try:
                project = Project.objects.get(name=pname, org=org)
                # Delete existing Variables and Streams
                project.variables.all().delete()
                project.streamids.all().delete()

            except Project.DoesNotExist:
                project = Project.objects.create(name=pname, created_by=admin, org=org)
                print('Created Project: {}'.format(project))

            self._projects.append(project)

        for item in self._device_info:
            logger.info(str(item))
            try:
                device_template = DeviceTemplate.objects.get(slug=item['device_template'])
            except DeviceTemplate.DoesNotExist:
                logger.error('Device Template not found: slug={}'.format(item['device_template']))
                sys.exit(status=0)
            try:
                sg = SensorGraph.objects.get(slug=item['sg'])
            except SensorGraph.DoesNotExist:
                logger.error('Sensor Graph not found: slug={}'.format(item['sg']))
                sys.exit(status=0)

            project = self._projects[item['project']]

            # Get or create device, and set up as Water Meter
            try:
                device = Device.objects.get(id=item['id'])
                device.template = device_template
                device.sg = sg
                device.label = item['label']
                device.active = True
                device.project = None
                device.org = None
                device.save()
            except Device.DoesNotExist:
                device = Device.objects.create_device(
                    id=item['id'],
                    project=None,
                    template=device_template,
                    label=item['label'],
                    sg=sg,
                    created_by=admin
                )

            # Claim device to Project
            device_claim(device=device, project=project, claimed_by=admin)

    def handle(self, *args, **options):

        admin = get_user_model().objects.first()
        if not admin:
            print('init-basic-data must be called first to create an Admin user')
            sys.exit()

        self._add_karma_test_projects(admin)

