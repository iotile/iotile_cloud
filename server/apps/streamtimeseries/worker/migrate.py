import datetime
import json
import logging

import boto3

from django.conf import settings
from django.db.models import Q

from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.streamtimeseries.models import StreamTimeSeriesEvent, StreamTimeSeriesValue
from apps.utils.aws.common import AWS_REGION
from apps.utils.data_helpers.convert import DataConverter

logger = logging.getLogger(__name__)


class MigrateDataAction(Action):
    """
    This action will migrate data/event to create its StreamTimeSeries counterpart
    It supports AWS Kinesis Firehose
    """
    _MODELS = {
        'data': {
            'old': StreamData,
            'model_converter': DataConverter.data_to_tsvalue,
            'firehose_converter': DataConverter.tsvalue_to_firehose,
            'new': StreamTimeSeriesValue,
            'firehose_stream_name_key': 'value',
        },
        'event': {
            'old': StreamEventData,
            'model_converter': DataConverter.event_to_tsevent,
            'firehose_converter': DataConverter.tsevent_to_firehose,
            'new': StreamTimeSeriesEvent,
            'firehose_stream_name_key': 'event',
        },
    }

    @classmethod
    def _arguments_ok(cls, args):
        return Action._check_arguments(
            args=args,
            task_name='MigrateDataAction',
            required=[
                'migration_type',
                'stream_slug',
            ],
            optional=[
                'start',
                'end',
            ],
        )

    def _datetime_handler(self, x):
        if isinstance(x, datetime.datetime):
            return x.isoformat()
        raise TypeError('Unknown type')

    def _write_stream_batch(self, records):
        try:
            response = self._firehose_client.put_record_batch(
                DeliveryStreamName=self._firehose_stream_name,
                Records=records
            )
            if 'FailedPutCount' in response and response['FailedPutCount']:
                logger.error('Firehose: {} upload failures detected'.format(response['FailedPutCount']))

        except Exception as e:
            logger.debug(e)
            logger.exception('Firehose: upload failures detected. {}'.format(str(e)[0:50]))

    def _send_to_firehose(self, data_entries, batch_num=490):
        batch_payload = []
        count = 1
        for item in data_entries:
            batch_item = {
                'Data': json.dumps(item, default=self._datetime_handler)
            }
            batch_payload.append(batch_item)
            count += 1
            if count == batch_num:
                logger.info('Uploading {} records'.format(batch_num))
                self._write_stream_batch(batch_payload)
                batch_payload = []
                count = 1

        if batch_payload:
            logger.info('Uploading final {} records'.format(len(batch_payload)))
            self._write_stream_batch(batch_payload)

    def _check_migration_type(self, migration_type):
        if migration_type not in self._MODELS:
            raise WorkerActionHardError(
                'Wrong migration type {}: should be in {}'.format(
                    migration_type, list(self._MODELS.keys())
                )
            )
        self._old_model = self._MODELS[migration_type]['old']
        self._model_converter = self._MODELS[migration_type]['model_converter']
        self._firehose_converter = self._MODELS[migration_type]['firehose_converter']
        self._new_model = self._MODELS[migration_type]['new']
        self._firehose_stream_name = getattr(
            settings,
            'FIREHOSE_STREAMTIMESERIES_STREAM_NAME'
        )[self._MODELS[migration_type]['firehose_stream_name_key']]

    def _build_list_of_new_objects(self, stream_slug, start, end):
        new_list = []
        q = Q(stream_slug=stream_slug)
        if start is not None:
            q &= Q(streamer_local_id__gte=start)
        if end is not None:
            q &= Q(streamer_local_id__lt=end)
        for old in self._old_model.objects.filter(q):
            new_list.append(self._model_converter(old))
        return new_list

    def _create_new_data(self, new_list):
        if self._use_firehose:
            firehose_data_entries = [self._firehose_converter(timeseries) for timeseries in new_list]
            logger.debug('Using firehose (Production - {})'.format(getattr(settings, 'PRODUCTION')))
            self._send_to_firehose(firehose_data_entries, batch_num=490)
        else:
            self._new_model.objects.bulk_create(new_list)
        logger.info('{} {} objects created'.format(len(new_list), self._new_model))

    def execute(self, arguments):
        super(MigrateDataAction, self).execute(arguments)
        if MigrateDataAction._arguments_ok(arguments):
            self._use_firehose = getattr(settings, 'USE_FIREHOSE_STREAMTIMESERIES') is True
            self._firehose_client = boto3.client('firehose', region_name=AWS_REGION)
            self._check_migration_type(arguments['migration_type'])

            new_list = self._build_list_of_new_objects(arguments['stream_slug'], arguments.get('start'), arguments.get('end'))

            # only if all the old data has been processed do we create the new data
            self._create_new_data(new_list)

    @classmethod
    def schedule(cls, args, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        """
        schedule function should always have at least args and queue_name as arguments
        :param args:
        :param queue_name:
        :param delay_seconds: optional
        :return:
        """
        module_name = cls.__module__
        class_name = cls.__name__
        if MigrateDataAction._arguments_ok(args):
            super(MigrateDataAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
