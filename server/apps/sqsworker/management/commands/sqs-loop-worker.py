from django.core.management.base import BaseCommand
from apps.sqsworker.workerhelper import Worker
from apps.utils.aws.sqs import get_queue_by_name
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--time', '-t', dest='wait_time', default='30',
                            help='Specify the wait time for checking SQS task queue (in seconds). Default is set to 120s')

        parser.add_argument('--queue-name', '-n', dest='queue_name', default='', help='Specify the SQS queue name')

    def handle(self, *args, **options):
        queue_name = ''
        if options.get('queue_name'):
            queue_name = options.get('queue_name')
        elif settings.SQS_WORKER_QUEUE_NAME:
            queue_name = settings.SQS_WORKER_QUEUE_NAME
        if queue_name != '':
            worker = Worker(get_queue_by_name(queue_name), int(options.get('wait_time')))
            worker.run()
        else:
            logger.error('SQS queue name not found')

