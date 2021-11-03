import logging
import sys

from django.core.management.base import BaseCommand

from apps.utils.data_helpers.manager import DataManager

logger = logging.getLogger(__name__)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--device', '-d', dest='device', help='Device slug', required=False)

        parser.add_argument('--all', '-a', action='store_true', dest='all', default=False,
                            help='Run for all device')

    def handle(self, *args, **options):
        device_slug = options.get('device')
        if options.get('all'):
            count_drt = DataManager.filter_qs('data', dirty_ts=True).update(status='drt')

            count_cln = DataManager.filter_qs('data', dirty_ts=False).update(status='cln')
        elif device_slug:
            count_drt = DataManager.filter_qs('data', dirty_ts=True, device_slug=device_slug).update(status='drt')

            count_cln = DataManager.filter_qs('data', dirty_ts=False, device_slug=device_slug).update(status='cln')
        else:
            logger.error("Please provide a device slug or select option --all")
            sys.exit()

        logger.info("Update {} data point to status dirty".format(count_drt))
        logger.info("Update {} data point to status clean".format(count_cln))
        logger.info("Done!")
