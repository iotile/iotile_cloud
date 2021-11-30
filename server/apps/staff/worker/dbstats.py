import logging

from django.conf import settings
from django.utils import timezone

from iotile_cloud.utils.gid import *

from apps.org.models import Org
from apps.physicaldevice.claim_utils import device_claim
from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.sensorgraph.models import SensorGraph
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerInternalError
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.helpers import StreamDataBuilderHelper
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.data_helpers.manager import DataManager

from ..dbstats import DbStats

logger = logging.getLogger(__name__)

SG_SLUG = 'development-v1-0-0'
DEVICE_GID = '0080'
DEVICE_LABEL = 'IOTile Cloud DB Metrics'
ORG_NAME = 'Arch Metrics'
ORG_SLUG = 'arch-metrics'

METRIC_ID = {
    'StreamData*': 'ff01',
    'StreamEvents*': 'ff02',
    'StreamerReports': 'ff03',
    'EnabledStreams': 'ff04'
}

class DbStatsAction(Action):
    _streams = {}
    _admin = None


    def _initialize_cloud_metrics_project(self, device, org):
        project = Project.objects.create(name=ORG_NAME, org=org, created_by=self._admin)

        try:
            sg = SensorGraph.objects.get(slug=SG_SLUG)
        except SensorGraph.DoesNotExist:
            raise WorkerInternalError('Expected Sensor Graph not found: {}'.format(SG_SLUG))

        # Create Variables
        for key in METRIC_ID.keys():
            StreamVariable.objects.create_variable(
                name=key,
                lid=int(METRIC_ID[key], 16),
                project=project,
                created_by=self._admin,
                web_only=True
            )

        # Claim Device
        device.label = DEVICE_LABEL
        device.sg = sg
        device.active = True
        device.save()
        device_claim(project=project, device=device, claimed_by=self._admin)
        StreamId.objects.create_after_new_device(device)

        return project

    def _check_arch_metrics_project_ok(self):
        device_slug = IOTileDeviceSlug(DEVICE_GID)

        try:
            device = Device.objects.get(slug=str(device_slug))
            self._admin = device.created_by
        except Device.DoesNotExist:
            raise WorkerInternalError('Expected Device for DB Stats not found: {}'.format(device_slug))

        try:
            org = Org.objects.get(slug=ORG_SLUG)
        except Org.DoesNotExist:
            logger.warning('Arch Metrics project not found: Creating')
            org = Org.objects.create_org(name='Arch Metrics', is_vendor=False, created_by=self._admin)

        if not device.project:
            logger.warning('{} device not claimed. Initialize'.format(ORG_NAME))
            project = self._initialize_cloud_metrics_project(device, org)
        else:
            project = device.project

        project_slug = IOTileProjectSlug(project.slug)
        assert project.org
        if project.org.slug != ORG_SLUG:
            raise WorkerInternalError('Project {0} not in expected Org : {1}'.format(project_slug, ORG_SLUG))
        else:
            stream_slug = IOTileStreamSlug()
            for key in METRIC_ID.keys():
                variable_slug = IOTileVariableSlug(METRIC_ID[key], project=project_slug)
                stream_slug.from_parts(project=project_slug, device=device_slug, variable=variable_slug)
                try:
                    self._streams[key] = StreamId.objects.get(slug=str(stream_slug))
                except StreamId.DoesNotExist:
                    raise WorkerInternalError('Stream {} not found'.format(stream_slug))

        return True

    def _post_data(self):

        s = DbStats()
        s.compute_stats()
        now = s.end

        payload = []
        helper = StreamDataBuilderHelper()
        if not now:
            now = timezone.now()

        for key in METRIC_ID.keys():
            if key in s.stats:
                value = s.stats[key]
                logger.info('{0} = {1}'.format(key, value))
                stream = self._streams[key]
                stream_data = helper.build_data_obj(
                    stream_slug = stream.slug,
                    timestamp = now,
                    int_value = value
                )
                payload.append(stream_data)

        if len(payload):
            DataManager.bulk_create('data', payload)

    def execute(self, arguments):
        super(DbStatsAction, self).execute(arguments)
        if 'ts' in arguments:
            ts = arguments['ts']
            logger.info('** Generating DbStats for last day: now={}'.format(ts))

            if self._check_arch_metrics_project_ok():
                self._post_data()

    @classmethod
    def schedule(cls, args, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        module_name = cls.__module__
        class_name = cls.__name__
        if 'ts' in args:
            super(DbStatsAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
        else:
            raise WorkerInternalError('Missing fields in argument payload.\nReceived args: {}\nRequired args fields: ts (now)'.format(
                    args))
