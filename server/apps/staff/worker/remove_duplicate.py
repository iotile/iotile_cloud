import logging

from django.conf import settings
from django.db.models import Count

from apps.physicaldevice.models import Device
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerInternalError
from apps.utils.data_helpers.manager import DataManager

logger = logging.getLogger(__name__)

DELAY_SECONDS = 10*60  # in seconds


class RemoveDuplicateAction(Action):

    def _remove_duplicate_stream(self, stream_slug):
        data = DataManager.filter_qs('data', stream_slug=stream_slug)
        visited = {}
        pending_delete_ids = []
        for item in data:
            if item.streamer_local_id:
                if item.streamer_local_id in visited:
                    pending_delete_ids.append(item.id)
                else:
                    visited[item.streamer_local_id] = True

        if len(pending_delete_ids):
            # Delete in chunks of 1000
            page_size = 1000
            pages = int(1 + (len(pending_delete_ids) / page_size))
            for page in range(pages):
                start = page * page_size
                end = ((page + 1) * page_size)
                logger.info('{}: Deleting page {}: [{}:{}]'.format(stream_slug, page+1, start, end))
                page_ids = pending_delete_ids[start:end]
                DataManager.filter_qs('data', id__in=page_ids).delete()

    def _remove_duplicate_device(self, device_slug):
        try:
            device = Device.objects.get(slug=device_slug)
        except Device.DoesNotExist:
            raise WorkerActionHardError("Device with slug {} not found".format(device_slug))
        if device:
            distinct_streams = DataManager.filter_qs(
                'data', device_slug=device.slug
            ).values('stream_slug').annotate(total=Count('id')).order_by(
                'streamer_local_id', 'stream_slug', 'timestamp'
            )
            for item in distinct_streams:
                logger.info("Remove duplicate for stream {}".format(item['stream_slug']))
                self._remove_duplicate_stream(item['stream_slug'])

    def execute(self, arguments):
        super(RemoveDuplicateAction, self).execute(arguments)
        if 'stream_slug' in arguments:
            self._remove_duplicate_stream(arguments['stream_slug'])
        elif 'device_slug' in arguments:
            self._remove_duplicate_device(arguments['device_slug'])
        else:
            raise WorkerActionHardError('Missing fields in arguments payload. Error comes from task RemoveDuplicateAction, received args: {}'.format(arguments))

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
        if 'stream_slug' in args or 'device_slug' in args:
            super(RemoveDuplicateAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
        else:
            raise WorkerInternalError('Missing fields in argument payload.\nReceived args: {}\nRequired args fields: device_slug or stream_slug'.format(args))
