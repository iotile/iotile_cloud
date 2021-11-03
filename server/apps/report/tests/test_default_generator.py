import json
from pprint import pprint
from datetime import timedelta
from django.utils import timezone, dateparse
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from apps.project.models import Project
from apps.physicaldevice.models import Device
from apps.utils.test_util import TestMixin
from apps.vartype.models import *
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.models import StreamData

from apps.utils.utest.devices import ThreeWaterMetersDeviceMocks

from ..models import *
from ..worker.report_generator import *
from ..generator.default.generator import DefaultReportGenerator, ReportColumn

user_model = get_user_model()


class ReportDefaultGeneratorActionTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.device_mocks = ThreeWaterMetersDeviceMocks()
        self.o2 = Org.objects.get(name='User Org')
        self.p1 = Project.objects.get(name='Project 1')
        self.p2 = Project.objects.get(name='Project 2')
        self.pd1 = self.p1.devices.first()

    def tearDown(self):
        self.device_mocks.tearDown()
        self.userTestTearDown()

    def testMock(self):
        self.device_mocks.testMock(self)

    def testGeneratorPath(self):
        rpt = UserReport.objects.create(label='RPT1', generator='default', org=self.o2, created_by=self.u2)
        module_path, class_name = ReportGenerator._generator_package_path(rpt.generator)
        self.assertEqual(module_path, 'apps.report.generator.default.generator')
        self.assertEqual(class_name, 'DefaultReportGenerator')
        generator_class = ReportGenerator.get_generator_class(rpt)
        rg = generator_class([], rpt, timezone.now(), timezone.now())
        self.assertTrue(isinstance(rg, DefaultReportGenerator))

    def testAggregateFunction(self):
        rpt = UserReport.objects.create(label='RPT1', generator='default', org=self.o2, created_by=self.u2)
        rg = DefaultReportGenerator([], rpt, timezone.now(), timezone.now())
        f = rg._aggregate(5, 6, 'sum')
        self.assertEqual(f, 11)
        f = rg._aggregate(5, 6, 'max')
        self.assertEqual(f, 6)
        f = rg._aggregate(5, 6, 'min')
        self.assertEqual(f, 5)
        f = rg._aggregate(rg._initial_value('sum'), 6, 'sum')
        self.assertEqual(f, 6)
        f = rg._aggregate(rg._initial_value('max'), -6, 'max')
        self.assertEqual(f, -6)
        f = rg._aggregate(rg._initial_value('min'), 6, 'min')
        self.assertEqual(f, 6)

    def testCheckVariable(self):
        col = ReportColumn({
            'name': 'foo',
            'type': 'foo',
            'units': 'foo',
            'aggregate': 'sum',
            'vars': [{'type': 'foo', 'lid': 'foo'}]
        })
        self.assertFalse(col._check_variable_item_ok('foo'))
        self.assertFalse(col._check_variable_item_ok(['foo']))
        self.assertFalse(col._check_variable_item_ok('5001'))
        self.assertFalse(col._check_variable_item_ok(['5001']))
        self.assertFalse(col._check_variable_item_ok([]))
        item = {
            'lid': '5001',
        }
        self.assertFalse(col._check_variable_item_ok(item))
        item = {
            'name': 'foo',
            'lid': 0x5001,
        }
        self.assertFalse(col._check_variable_item_ok(item))
        item['lid'] = '501'
        self.assertFalse(col._check_variable_item_ok(item))

        item['lid'] = '5001'
        self.assertTrue(col._check_variable_item_ok(item))

        # Test Hex
        item['lid'] = '500f'
        self.assertTrue(col._check_variable_item_ok(item))

    def testBadSources(self):
        rpt1 = UserReport.objects.create(
            label='RPT1',
            config={'cols': []},
            sources=['foo'],
            created_by=self.u2,
            org=self.o2
        )

        action = ReportGeneratorAction()
        action._reset(rpt1)
        end = timezone.now()
        start = end - timedelta(hours=2)
        rg = DefaultReportGenerator(action._msgs, rpt1, start, end)
        action._process_data_sources(rg, rpt1.sources)
        self.assertEqual(len(action._sources), 0)

        rpt1.sources = ['p--foo']
        action._reset(rpt1)
        action._process_data_sources(rg, rpt1.sources)
        self.assertEqual(len(action._sources), 0)

        rpt1.sources = ['d--foo']
        action._reset(rpt1)
        action._process_data_sources(rg, rpt1.sources)
        self.assertEqual(len(action._sources), 0)

        rpt1.sources = ['d--foo--bar']
        action._reset(rpt1)
        action._process_data_sources(rg, rpt1.sources)
        self.assertEqual(len(action._sources), 0)

        rpt1.sources = ['s--foo']
        action._reset(rpt1)
        action._process_data_sources(rg, rpt1.sources)
        self.assertEqual(len(action._sources), 0)
        self.assertEqual(len(action._msgs), 1)

    def testBadVariable(self):
        config = {
            'cols': [
                {
                    'name': 'Water Usage',
                    'vars': [
                        {'lid': '5001', 'name': 'IO 1'},
                        {'lid': 'foo', 'name': 'IO 2'}
                    ],
                    'aggregate': 'sum',
                    'type': 'water-meter-volume',
                    'units': 'out--water-meter-volume--acre-feet'
                }
            ]
        }
        rpt1 = UserReport.objects.create(
            label='RPT1',
            config=config,
            sources=[self.p1.slug],
            created_by=self.u2,
            org=self.o2
        )

        action = ReportGeneratorAction()
        action._reset(rpt1)
        end = timezone.now()
        start = end - timedelta(hours=2)
        rg = DefaultReportGenerator(action._msgs, rpt1, start, end)
        rg.process_config()
        self.assertEqual(len(action._msgs), 1)
        self.assertEqual(len(rg._cols), 1)
        self.assertEqual(len(rg._cols[0].lids), 1)
        self.assertEqual(rg._cols[0].lids[0], '5001')

        rpt1.config['cols'][0]['vars'][0]['lid'] = 0x5001
        action._reset(rpt1)
        rg = DefaultReportGenerator(action._msgs, rpt1, start, end)
        rg.process_config()
        self.assertEqual(len(rg._cols), 1)
        self.assertEqual(len(rg._cols[0].lids), 0)
        self.assertEqual(len(action._msgs), 2)

    def testVariableFilters(self):
        config = {
            'cols': [
                {
                    'name': 'Water Usage',
                    'vars': [
                        {'lid': '5001', 'name': 'IO 1'},
                        {'lid': '5002', 'name': 'IO 2'}
                    ],
                    'aggregate': 'sum',
                    'type': 'water-meter-volume',
                    'units': 'out--water-meter-volume--acre-feet'
                }
            ]
        }
        rpt1 = UserReport.objects.create(
            label='RPT1',
            config=config,
            sources=[self.pd1.slug, self.p2.slug],
            created_by=self.u2,
            org=self.o2
        )

        action = ReportGeneratorAction()
        action._reset(rpt1)
        end = timezone.now()
        start = end - timedelta(hours=2)
        rg = DefaultReportGenerator(action._msgs, rpt1, start, end)
        rg.process_config()
        action._process_data_sources(rg, rpt1.sources)
        self.assertEqual(len(rg._cols), 1)
        self.assertEqual(len(rg._cols[0].lids), 2)
        self.assertEqual(len(rg._cols[0].stream_slugs), 6)

        rpt1.config['cols'][0]['vars'] = [{'lid': '5001', 'name': 'IO 1'}]
        action._reset(rpt1)
        rg = DefaultReportGenerator(action._msgs, rpt1, start, end)
        rg.process_config()
        action._process_data_sources(rg, rpt1.sources)
        self.assertEqual(len(rg._cols), 1)
        self.assertEqual(len(rg._cols[0].lids), 1)
        self.assertEqual(rg._cols[0].lids[0], '5001')
        self.assertEqual(len(rg._cols[0].stream_slugs), 3)
        for stream in rg._cols[0].stream_slugs:
            self.assertEqual(stream.split('--')[3], '5001')
        self.assertEqual(len(action._msgs), 0)

    def testBasicProcessReportAction(self):
        self.assertEqual(StreamId.objects.count(), 6)
        config = {
            'cols': [
                {
                    'name': 'Water Usage',
                    'vars': [
                        {'lid': '5001', 'name': 'IO 1'},
                        {'lid': '5002', 'name': 'IO 2'}
                    ],
                    'aggregate': 'sum',
                    'type': 'water-meter-volume',
                    'units': 'out--water-meter-volume--gallons'
                }
            ]
        }
        rpt1 = UserReport.objects.create(
            label='RPT1',
            interval='d',
            config=config,
            sources=[self.pd1.slug, self.p2.slug],
            created_by=self.u2,
            org=self.o2
        )

        action = ReportGeneratorAction()
        end = timezone.now()
        start = end - timedelta(hours=2)
        action.process_user_report(rpt1, start, end, rpt1.sources)
        self.assertEqual(len(action._msgs), 0)

    def testBasicSumColumn(self):
        self.assertEqual(StreamId.objects.count(), 6)
        config = {
            'cols': [
                {
                    'name': 'Water Usage',
                    'vars': [
                        {'lid': '5001', 'name': 'IO 1'},
                        {'lid': '5002', 'name': 'IO 2'}
                    ],
                    'aggregate': 'sum',
                    'type': 'water-meter-volume',
                    'units': 'out--water-meter-volume--gallons'
                }
            ]
        }
        rpt1 = UserReport.objects.create(
            label='RPT1',
            interval='d',
            config=config,
            sources=[self.pd1.slug, self.p2.slug],
            created_by=self.u2,
            org=self.o2
        )

        action = ReportGeneratorAction()
        action._reset(rpt1)
        end = timezone.now()
        start = end - timedelta(hours=2)
        rg = DefaultReportGenerator(action._msgs, rpt1, start, end)
        rg.process_config()
        action._process_data_sources(rg, rpt1.sources)
        ctx = rg._compute_report_context()
        self.assertEqual(ctx['label'], rpt1.label)
        self.assertEqual(len(ctx['total']), 1)
        self.assertAlmostEqual(ctx['total'][0]['value'], 11.887, delta=0.002)
        self.assertEqual(ctx['total'][0]['units'], 'G')

    def testTwoSumColumn1(self):
        self.assertEqual(StreamId.objects.count(), 6)
        config = {
            'cols': [
                {
                    'name': 'Water Usage1',
                    'vars': [
                        {'lid': '5001', 'name': 'IO 1'}
                    ],
                    'aggregate': 'sum',
                    'type': 'water-meter-volume',
                    'units': 'out--water-meter-volume--gallons'
                },
                {
                    'name': 'Water Usage2',
                    'vars': [
                        {'lid': '5002', 'name': 'IO 2'}
                    ],
                    'aggregate': 'sum',
                    'type': 'water-meter-volume',
                    'units': 'out--water-meter-volume--liters'
                }
            ]
        }
        rpt1 = UserReport.objects.create(
            label='RPT1',
            interval='d',
            config=config,
            sources=[self.pd1.slug, self.p2.slug],
            created_by=self.u2,
            org=self.o2
        )

        action = ReportGeneratorAction()
        action._reset(rpt1)
        end = timezone.now()
        start = end - timedelta(hours=2)
        rg = DefaultReportGenerator(action._msgs, rpt1, start, end)
        rg.process_config()
        action._process_data_sources(rg, rpt1.sources)
        ctx = rg._compute_report_context()
        # pprint(ctx)
        self.assertEqual(ctx['label'], rpt1.label)
        self.assertEqual(len(ctx['total']), 2)
        self.assertAlmostEqual(ctx['total'][0]['value'], 7.660, delta=0.002)
        self.assertEqual(ctx['total'][0]['units'], 'G')
        self.assertAlmostEqual(ctx['total'][1]['value'], 16.0, delta=0.002)
        self.assertEqual(ctx['total'][1]['units'], 'L')

    def testTwoSumColumn2(self):
        self.assertEqual(StreamId.objects.count(), 6)
        config = {
            'cols': [
                {
                    'name': 'Water Usage1',
                    'vars': [
                        {'lid': '5001', 'name': 'IO 1'},
                        {'lid': '5002', 'name': 'IO 2'}
                    ],
                    'aggregate': 'sum',
                    'type': 'water-meter-volume',
                    'units': 'out--water-meter-volume--gallons'
                },
                {
                    'name': 'Water Usage2',
                    'vars': [
                        {'lid': '5001', 'name': 'IO 1'},
                        {'lid': '5002', 'name': 'IO 2'}
                    ],
                    'aggregate': 'sum',
                    'type': 'water-meter-volume',
                    'units': 'out--water-meter-volume--liters'
                }
            ]
        }
        rpt1 = UserReport.objects.create(
            label='RPT1',
            interval='d',
            config=config,
            sources=[self.pd1.slug, self.p2.slug],
            created_by=self.u2,
            org=self.o2
        )

        action = ReportGeneratorAction()
        action._reset(rpt1)
        end = timezone.now()
        start = end - timedelta(hours=2)
        rg = DefaultReportGenerator(action._msgs, rpt1, start, end)
        rg.process_config()
        action._process_data_sources(rg, rpt1.sources)
        ctx = rg._compute_report_context()
        self.assertEqual(ctx['label'], rpt1.label)
        self.assertEqual(len(ctx['total']), 2)
        self.assertAlmostEqual(ctx['total'][0]['value'], 11.8877, delta=0.002)
        self.assertEqual(ctx['total'][0]['units'], 'G')
        self.assertEqual(ctx['total'][1]['value'], 45.0)
        self.assertEqual(ctx['total'][1]['units'], 'L')
        for p in ctx['project_list']:
            if p['name'] == 'Project 1':
                self.assertAlmostEqual(p['total'][0]['value'], 6.8684, delta=0.002)
                self.assertEqual(p['total'][1]['value'], 26.0)
            if p['name'] == 'Project 2':
                self.assertAlmostEqual(p['total'][0]['value'], 5.0192, delta=0.002)
                self.assertEqual(p['total'][1]['value'], 19.0)

    def testMaxMinColumn(self):
        self.assertEqual(StreamId.objects.count(), 6)

        d1 = self.p1.devices.first()
        d2 = self.p2.devices.first()
        s2 = d1.streamids.last()
        s3 = d2.streamids.first()

        config = {
            'cols': [
                {
                    'name': 'Max',
                    'vars': [
                        {'lid': '5001', 'name': 'IO 1'},
                        {'lid': '5002', 'name': 'IO 2'}
                    ],
                    'aggregate': 'max',
                    'type': 'water-meter-volume',
                    'units': 'out--water-meter-volume--liters'
                },
                {
                    'name': 'Min',
                    'vars': [
                        {'lid': '5001', 'name': 'IO 1'},
                        {'lid': '5002', 'name': 'IO 2'}
                    ],
                    'aggregate': 'min',
                    'type': 'water-meter-volume',
                    'units': 'out--water-meter-volume--liters'
                }
            ]
        }
        rpt1 = UserReport.objects.create(
            label='RPT1',
            interval='d',
            config=config,
            sources=[s2.slug, s3.slug],
            created_by=self.u2,
            org=self.o2
        )

        action = ReportGeneratorAction()
        action._reset(rpt1)
        end = timezone.now()
        start = end - timedelta(hours=2)
        rg = DefaultReportGenerator(action._msgs, rpt1, start, end)
        rg.process_config()
        action._process_data_sources(rg, rpt1.sources)
        ctx = rg._compute_report_context()
        # pprint(ctx)
        self.assertEqual(ctx['label'], rpt1.label)
        self.assertEqual(ctx['headers'][0], 'Max')
        self.assertEqual(ctx['headers'][1], 'Min')
        self.assertEqual(ctx['total'][0]['value'], 8.0)
        self.assertEqual(ctx['total'][0]['units'], 'L')
        self.assertEqual(ctx['total'][1]['value'], 5.0)
        self.assertEqual(ctx['total'][1]['units'], 'L')
        for p in ctx['project_list']:
            if p['name'] == 'Project 1':
                self.assertEqual(p['total'][0]['value'], 6.0)
                self.assertEqual(p['total'][1]['value'], 5.0)
            if p['name'] == 'Project 2':
                self.assertEqual(p['total'][0]['value'], 8.0)
                self.assertEqual(p['total'][1]['value'], 6.0)
