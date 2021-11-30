import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import formated_timedelta

from ..models import *

user_model = get_user_model()

class UserReportTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        UserReport.objects.all().defer()
        self.orgTestTearDown()
        self.userTestTearDown()
        self.deviceTemplateTestTearDown()

    def testBasics(self):
        rpt = UserReport.objects.create(label='RPT1', org=self.o2, created_by=self.u2)
        self.assertEqual(rpt.generator, 'default')
        self.assertIsNotNone(rpt.config)
        self.assertIsNotNone(rpt.config['cols'])
        self.assertIsNotNone(rpt.sources)
        self.assertEqual(len(rpt.config['cols']), 0)
        self.assertEqual(len(rpt.sources), 0)
        config = {
            'cols': [
                {
                    'name': 'Water Usage',
                    'vars': [
                        {'lid': '5001', 'name': 'IO 1'},
                        {'lid': '5002', 'name': 'IO 2'}
                    ],
                    'type': 'water-meter-volume',
                    'units': 'out--water-meter-volume--gallons'
                }
            ]
        }
        rpt = UserReport.objects.create(
            label='RPT1', config=config, sources=['p--0001', 'd--0002'],
            org=self.o2, created_by=self.u2
        )
        self.assertIsNotNone(rpt.config)
        self.assertIsNotNone(rpt.config['cols'])
        self.assertIsNotNone(rpt.sources)
        self.assertEqual(len(rpt.config['cols']), 1)
        self.assertEqual(len(rpt.config['cols'][0]['vars']), 2)
        self.assertEqual(len(rpt.sources), 2)

    def testObjectAccess(self):
        r1 = UserReport.objects.create(label='RPT 1', created_by=self.u2, org=self.o2)
        r2 = UserReport.objects.create(label='RPT 2', created_by=self.u3, org=self.o3)
        self.assertTrue(r1.has_access(self.u1))
        self.assertTrue(r1.has_access(self.u2))
        self.assertFalse(r1.has_access(self.u3))
        self.assertTrue(r2.has_access(self.u1))
        self.assertFalse(r2.has_access(self.u2))
        self.assertTrue(r2.has_access(self.u3))

    def test_delta_format(self):
        self.assertEqual(formated_timedelta('unk'), 'unk')
        self.assertEqual(formated_timedelta('0:0:0'), '0:0:0')
        self.assertEqual(formated_timedelta(5), '0:0:5')
        self.assertEqual(formated_timedelta(5.0), '0:0:5')
        self.assertEqual(formated_timedelta(65), '0:1:5')
        self.assertEqual(formated_timedelta(3605), '1:0:5')
        self.assertEqual(formated_timedelta(3600*30+65), '30:1:5')
