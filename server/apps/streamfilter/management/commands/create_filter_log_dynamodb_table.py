import logging
import sys
from django.core.management.base import BaseCommand

from apps.streamfilter.dynamodb import DynamoFilterLogModel, create_filter_log_table_if_needed
logger = logging.getLogger(__name__)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--delete', action='store_true', dest='delete', default=False,
                            help='Delete existing table (requires confirmation)')

    def handle(self, *args, **options):

        if options['delete'] and DynamoFilterLogModel.exists():
            count = DynamoFilterLogModel.count()
            table_name = DynamoFilterLogModel.Meta.table_name
            print('-------------------------------------------------------------------')
            print('DANGER: You are about to delete an un-backed-up database')
            print('        Table has {} items'.format(count))
            print('        Type table name ({}) to confirm'.format(table_name))
            choice = input('> ')
            print('-------------------------------------------------------------------')
            if choice != table_name:
                print('-> Nothing done')
                sys.exit()
            DynamoFilterLogModel.delete_table()

        create_filter_log_table_if_needed()
