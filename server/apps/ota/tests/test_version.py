import datetime
import json

import dateutil.parser

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()


class DeviceVersionAttributeTests(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

        self.create_basic_test_devices()

        self.v1 = DeviceVersionAttribute.objects.create(
            device=self.pd1,
            type='os',
            tag=1024,
            major_version=1,
            minor_version=1,
            streamer_local_id=4567,
            updated_ts=timezone.now()
        )
        self.v2 = DeviceVersionAttribute.objects.create(
            device=self.pd1,
            type='os',
            tag=1024,
            major_version=1,
            minor_version=2,
            streamer_local_id=5678,
            updated_ts=timezone.now()
        )


    def tearDown(self):
        DeviceScript.objects.all().delete()
        DeploymentRequest.objects.all().delete()
        DeploymentAction.objects.all().delete()
        DeviceVersionAttribute.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasic(self):
        obj = DeviceVersionAttribute.objects.create(
            device=self.pd1,
            type='os',
            tag=5,
            major_version=0,
            minor_version=1
        )
        self.assertIsNotNone(obj)
        self.assertEqual(str(obj), 'Version({0}) = os:5:v0.1'.format(self.pd1.id))
        self.assertEqual(obj.version, 'v0.1')
        self.assertEqual(obj.version_number, 0.1)

    def testLastVersionQuery(self):
        qs = DeviceVersionAttribute.objects.filter(device=self.pd1)
        self.assertEqual(qs.first().id, self.v1.id)
        self.assertEqual(qs.last().id, self.v2.id)
        self.assertEqual(qs.first().type, 'os')
        self.assertEqual(qs.last().type, 'os')

        obj = DeviceVersionAttribute.objects.filter(device=self.pd1).earliest('updated_ts')
        self.assertEqual(obj.id, self.v1.id)
        obj = DeviceVersionAttribute.objects.filter(device=self.pd1).latest('updated_ts')
        self.assertEqual(obj.id, self.v2.id)

        qs = DeviceVersionAttribute.objects.current_device_version_qs(device=self.pd1)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().id, self.v2.id)

        v3 = DeviceVersionAttribute.objects.create(
            device=self.pd1,
            type='os',
            tag=1024,
            major_version=1,
            minor_version=3,
            streamer_local_id=6678,
            updated_ts=timezone.now()
        )
        qs = DeviceVersionAttribute.objects.current_device_version_qs(device=self.pd1)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().id, v3.id)

        v4 = DeviceVersionAttribute.objects.create(
            device=self.pd1,
            type='sg',
            tag=1027,
            major_version=1,
            minor_version=0,
            streamer_local_id=6678,
            updated_ts=timezone.now()
        )
        qs = DeviceVersionAttribute.objects.current_device_version_qs(device=self.pd1)
        self.assertEqual(qs.count(), 2)
        self.assertEqual(qs.filter(type='os').first().id, v3.id)
        self.assertEqual(qs.filter(type='sg').first().id, v4.id)

        last = DeviceVersionAttribute.objects.last_device_version(device=self.pd1, type='os')
        self.assertEqual(last.id, v3.id)

        v4 = DeviceVersionAttribute.objects.create(
            device=self.pd1,
            type='os',
            tag=1024,
            major_version=1,
            minor_version=4,
            streamer_local_id=6680,
            updated_ts=timezone.now()
        )

        last = DeviceVersionAttribute.objects.last_device_version(device=self.pd1, type='os')
        self.assertEqual(last.id, v4.id)

