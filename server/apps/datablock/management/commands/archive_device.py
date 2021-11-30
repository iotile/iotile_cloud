import logging
import sys

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.datablock.models import DataBlock
from apps.datablock.worker.archive_device_data import ArchiveDeviceDataAction
from apps.physicaldevice.models import Device

logger = logging.getLogger(__name__)

class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('device', type=str)

    def handle(self, *args, **options):

        admin = get_user_model().objects.first()
        if not admin:
            logger.error('No Admin User found')
            sys.exit()

        device_slug = options['device']

        device = None
        try:
            device = Device.objects.get(slug=device_slug)
        except Device.DoesNotExist:
            logger.error('Device {} does not exist'.format(device_slug))

        if device and device.active and device.project:
            block_num = device.data_blocks.count() + 1
            action = ArchiveDeviceDataAction()
            block = DataBlock.objects.create(org=device.org,
                                             title='Device {0}. Archive {1}'.format(device.slug, block_num),
                                             device=device,
                                             block=block_num,
                                             created_by=admin)
            logger.info('Block = {}'.format(block))
            action.execute(arguments={'data_block_slug': block.slug})

            logger.info('Device {0} was archived. Block: {1}'.format(device_slug, block.slug))
        else:
            logger.error('Device {0} not active or claimed'.format(device_slug))
