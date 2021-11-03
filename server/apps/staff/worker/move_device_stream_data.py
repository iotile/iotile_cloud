import logging
from datetime import timedelta

from django.conf import settings
from django.utils.dateparse import parse_datetime

from apps.physicaldevice.models import Device
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerInternalError
from apps.stream.models import StreamId
from apps.utils.aws.redshift import get_ts_from_redshift
from apps.utils.data_helpers.manager import DataManager

logger = logging.getLogger(__name__)


class MoveDeviceStreamDataAction(Action):

    def _get_data_for_period_qs(self, filter, qs):
        start = end = None
        if 'start' in filter:
            start = filter['start']
        if 'end' in filter:
            end = filter['end']
        if start:
            qs = qs.filter(timestamp__gte=start)
        if end:
            qs = qs.filter(timestamp__lt=end)

        return qs

    def _migrate_stream_data(self, dev0, dev1, filter):
        logger.info('Moving DataStreams from {0} to {1}'.format(dev0, dev1))
        assert dev0 and dev1
        assert dev0.project == dev1.project

        # Assumes the _migrate_streams function has been called and new the block has streams
        for s0 in dev0.streamids.filter(block__isnull=True):

            try:
                s1 = StreamId.objects.get(project=s0.project, device=dev1, variable=s0.variable, block__isnull=True)
            except StreamId.DoesNotExist:
                s1 = StreamId.objects.clone_into_another_device(s0, dev1)

            # This will not update any old data from dev0
            # to the new dev1
            data_qs = DataManager.filter_qs('data', stream_slug=s0.slug)
            data_qs = self._get_data_for_period_qs(filter=filter, qs=data_qs)
            data_qs.update(device_slug=dev1.slug, stream_slug=s1.slug)

            # Same for Events
            data_qs = DataManager.filter_qs('event', stream_slug=s0.slug)
            data_qs = self._get_data_for_period_qs(filter=filter, qs=data_qs)
            data_qs.update(device_slug=dev1.slug, stream_slug=s1.slug)

    def execute(self, arguments):
        super(MoveDeviceStreamDataAction, self).execute(arguments)
        if 'dev0_slug' in arguments and 'dev1_slug' in arguments:
            try:
                dev0 = Device.objects.get(slug=arguments['dev0_slug'])
            except Device.DoesNotExist:
                raise WorkerActionHardError("Device with slug {} not found !".format(arguments['dev0_slug']))

            try:
                dev1 = Device.objects.get(slug=arguments['dev1_slug'])
            except Device.DoesNotExist:
                raise WorkerActionHardError("Device with slug {} not found !".format(arguments['dev1_slug']))

            filter = {}
            if 'start' in arguments:
                filter['start'] = parse_datetime(arguments['start'])
            if 'end' in arguments:
                filter['end'] = parse_datetime(arguments['end'])

            self._migrate_stream_data(dev0, dev1, filter)

        else:
            raise WorkerInternalError('Missing fields in arguments payload. Error comes from task HandleDelayAction, received args: {}'.format(arguments))

    @classmethod
    def schedule(cls, args, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        module_name = cls.__module__
        class_name = cls.__name__
        if 'dev0_slug' in args or 'dev1_slug' in args:
            super(MoveDeviceStreamDataAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
        else:
            raise WorkerInternalError('Missing fields in argument payload.\nReceived args: {}\nRequired args fields: dev0_slug and dev1_slug)'.format(
                args))
