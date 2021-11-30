import json
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_datetime

from iotile_cloud.utils.gid import IOTileBlockSlug, IOTileDeviceSlug, IOTileProjectSlug, IOTileStreamSlug

from apps.datablock.models import DataBlock
from apps.org.models import Org
from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError
from apps.stream.models import StreamId
from apps.utils.timezone_utils import str_utc

from ..generator.base import ReportGenerator
from ..generator.config import rpt_configuration_requirements_met
from ..models import UserReport

logger = logging.getLogger(__name__)

WORKER_QUEUE_NAME = getattr(settings, 'SQS_WORKER_QUEUE_NAME')


class ReportGeneratorAction(Action):
    _rpt = None
    _sources = []
    _msgs = []
    _arguments = {}

    @classmethod
    def _arguments_ok(self, args):
        return Action._check_arguments(
            args=args, task_name='ReportGeneratorAction',
            required=['rpt',], optional=['start', 'end', 'sources', 'attempt']
        )

    def _reset(self, rpt):
        self._rpt = rpt
        self._sources = []
        self._msgs = []
        self.streams = []

    def _reschedule(self, delay_seconds):
        if 'attempt' in self._arguments:
            self._arguments['attempt'] -= 1
            logger.info(str(self._arguments))
            if self._arguments['attempt'] > 0:
                ReportGeneratorAction.schedule(args=self._arguments, delay_seconds=delay_seconds)

    def _process_project_source(self, slug):
        try:
            project_slug = IOTileProjectSlug(slug)
        except ValueError:
            self._msgs.append('Project slug is illegal: {}'.format(slug))
            return None
        try:
            project = Project.objects.get(slug=str(project_slug))
        except Project.DoesNotExist:
            # logger.error('Project does not exist: {}'.format(project_slug))
            self._msgs.append('Project does not exist: {}'.format(project_slug))
            return None

        self._sources.append(project_slug)
        qs = StreamId.objects.filter(enabled=True, project=project, block__isnull=True).select_related('project', 'device')
        return qs

    def _process_device_source(self, slug):
        try:
            device_slug = IOTileDeviceSlug(slug)
        except ValueError:
            self._msgs.append('Device Slug is incorrect: {}'.format(slug))
            return None

        try:
            device = Device.objects.get(slug=str(device_slug))
        except Device.DoesNotExist:
            # logger.error('Project does not exist: {}'.format(project_slug))
            self._msgs.append('Device does not exist: {}'.format(device_slug))
            return None

        self._sources.append(device_slug)
        qs = StreamId.objects.filter(enabled=True, device=device, block__isnull=True).select_related('project', 'device')
        return qs

    def _process_datablock_source(self, slug):
        try:
            block_slug = IOTileBlockSlug(slug)
        except ValueError:
            self._msgs.append('DataBlock Slug is incorrect: {}'.format(slug))
            return None

        try:
            block = DataBlock.objects.get(slug=str(block_slug))
        except Device.DoesNotExist:
            # logger.error('Project does not exist: {}'.format(project_slug))
            self._msgs.append('DataBlock does not exist: {}'.format(block_slug))
            return None

        self._sources.append(block_slug)
        qs = StreamId.objects.filter(enabled=True, device=block.device, block=block).select_related('project', 'device')
        return qs

    def _process_stream_source(self, slug):
        try:
            stream_slug = IOTileStreamSlug(slug)
        except ValueError:
            self._msgs.append('Stream not found: {}'.format(slug))
            return None

        self._sources.append(stream_slug)
        qs = StreamId.objects.filter(enabled=True, slug=str(stream_slug)).select_related('project', 'device')
        return qs

    def _process_data_sources(self, rg, orginal_sources):
        assert orginal_sources and len(orginal_sources)
        factory = {
            'p--': self._process_project_source,
            'd--': self._process_device_source,
            'b--': self._process_datablock_source,
            's--': self._process_stream_source
        }

        for src in orginal_sources:
            prefix = src[0:3]
            if prefix in factory:
                qs = factory[prefix](src)
                if qs:
                    rg.add_streams_for_qs(qs=qs)
            else:
                self._msgs.append('Illegal source: {}'.format(src))

    def _get_dynamic_report_generator(self, start, end, orginal_sources):

        try:
            report_class = ReportGenerator.get_generator_class(self._rpt)
        except Exception as e:
            raise WorkerActionHardError(e)

        rg = report_class(self._msgs, self._rpt, start, end, orginal_sources)
        rg.reschedule_callback = self._reschedule
        return rg

    def process_user_report(self, rpt, start, end, orginal_sources):
        logger.info('Processing report: {0} - {1}'.format(rpt.org.slug, rpt.label))

        # 1. Make sure we clear out all data
        self._reset(rpt)
        rg = self._get_dynamic_report_generator(start, end, orginal_sources)

        # 2. Process configuration
        assert rpt_configuration_requirements_met(
            generator=self._rpt.generator,
            config=self._rpt.config,
            sources=orginal_sources
        )
        rg.process_config()

        # 3. Process report data sources (either projects or devices)
        self._process_data_sources(rg, orginal_sources)

        # 4. Generate User Report
        rg.generate_user_report()

    def execute(self, arguments):
        super(ReportGeneratorAction, self).execute(arguments)
        if ReportGeneratorAction._arguments_ok(arguments):

            self._arguments = arguments

            try:
                rpt = UserReport.objects.get(id=arguments['rpt'])
            except UserReport.DoesNotExist:
                raise WorkerActionHardError('Report not found: {}'.format(arguments['rpt']))

            start = end = None
            if 'start' in arguments and arguments['start']:
                start = parse_datetime(arguments['start'])
            if 'end' in arguments and arguments['end']:
                end = parse_datetime(arguments['end'])
            if 'sources' in arguments and arguments['sources']:
                # If task includes sources, then overwrite report sources
                if not isinstance(arguments['sources'], list):
                    raise WorkerActionHardError('ReportGeneratorAction sources field must be an array. Got: {}'.format(arguments['sources']))
                orginal_sources = arguments['sources']
            else:
                orginal_sources = rpt.sources

            self.process_user_report(rpt, start, end, orginal_sources)

    @classmethod
    def schedule(cls, args=None, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        module_name = cls.__module__
        class_name = cls.__name__
        if ReportGeneratorAction._arguments_ok(args):
            super(ReportGeneratorAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)


class SummaryReportGeneratorAction(ReportGeneratorAction):

    @classmethod
    def _arguments_ok(self, args):
        required = ['config', 'sources', 'generator', 'notification_recipients', 'org', 'user']
        optional = ['start', 'end', 'attempt']
        return Action._check_arguments(
            args=args, task_name='ReportGeneratorForFilterAction',
            required=required, optional=optional
        )

    def _reschedule(self, delay_seconds):
        if 'attempt' in self._arguments:
            self._arguments['attempt'] -= 1
            logger.info(str(self._arguments))
            if self._arguments['attempt'] > 0:
                SummaryReportGeneratorAction.schedule(args=self._arguments, delay_seconds=delay_seconds)

    def execute(self, arguments):
        super(ReportGeneratorAction, self).execute(arguments)
        if SummaryReportGeneratorAction._arguments_ok(arguments):

            self._arguments = arguments

            try:
                org = Org.objects.get(slug=arguments['org'])
            except Org.DoesNotExist:
                raise WorkerActionHardError('Org {} not found'.format(arguments['org']))

            user_model = get_user_model()
            try:
                user = user_model.objects.get(slug=arguments['user'])
            except user_model.DoesNotExist:
                raise WorkerActionHardError('User {} not found'.format(arguments['user']))

            rpt = UserReport(
                label='Generated Report',
                generator=arguments['generator'],
                config=arguments['config'],
                notification_recipients=arguments['notification_recipients'],
                org=org,
                created_by=user
            )

            start = end = None
            if 'start' in arguments and arguments['start']:
                start = parse_datetime(arguments['start'])
            if 'end' in arguments and arguments['end']:
                end = parse_datetime(arguments['end'])

            self.process_user_report(rpt, start, end, arguments['sources'])

    @classmethod
    def schedule(cls, args=None, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        module_name = cls.__module__
        class_name = cls.__name__
        if SummaryReportGeneratorAction._arguments_ok(args):
            super(ReportGeneratorAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)

