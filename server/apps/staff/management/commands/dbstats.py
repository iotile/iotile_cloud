import pprint
import logging
from django.utils import timezone
from django.core.management.base import BaseCommand
from apps.staff.worker.dbstats import DbStatsAction
from apps.utils.timezone_utils import str_utc

logger = logging.getLogger(__name__)


class Command(BaseCommand):


    def handle(self, *args, **options):
        action = DbStatsAction()

        try:
            action.execute({ 'ts': str_utc(timezone.now()) })
        except Exception as e:
            logger.error(e)
