import datetime
import json

import dateutil.parser

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.devicescript.models import DeviceScript
from apps.utils.test_util import TestMixin

from ..models import *
from ..utils.selection import DeploymentDeviceSelectionHelper, DeviceSelectionRule

user_model = get_user_model()


class DeploymentRequestTests(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

        self.create_basic_test_devices()

    def tearDown(self):
        Device.objects.all().delete()
        Fleet.objects.all().delete()
        DeviceScript.objects.all().delete()
        DeploymentRequest.objects.all().delete()
        DeviceVersionAttribute.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testRuleParser(self):
        pd3 = Device.objects.create_device(project=self.p1, label='d4',
                                           template=self.dt2, created_by=self.u1, claimed_by=self.u2)
        v1 = DeviceVersionAttribute.objects.create(
            device=self.pd1, type='os', tag=self.pd1.template.os_tag,
            major_version=0, minor_version=1
        )
        v2 = DeviceVersionAttribute.objects.create(
            device=self.pd1, type='os', tag=self.pd1.template.os_tag,
            major_version=1, minor_version=1
        )
        v3 = DeviceVersionAttribute.objects.create(
            device=self.pd1, type='os', tag=self.pd1.template.os_tag,
            major_version=1, minor_version=2
        )
        v4 = DeviceVersionAttribute.objects.create(
            device=pd3, type='os', tag=pd3.template.os_tag,
            major_version=1, minor_version=2
        )
        v5 = DeviceVersionAttribute.objects.create(
            device=pd3, type='os', tag=pd3.template.os_tag,
            major_version=2, minor_version=0
        )

        helper1 = DeviceSelectionRule('os_tag:eq:1024')
        q = helper1.q()
        qs = DeviceVersionAttribute.objects.filter(q)
        self.assertEqual(qs.count(), 3)

        helper1 = DeviceSelectionRule('os_tag:eq:1025')
        q = helper1.q()
        qs = DeviceVersionAttribute.objects.filter(q)
        self.assertEqual(qs.count(), 2)

        helper1 = DeviceSelectionRule('os_version:eq:1.1')
        q = helper1.q()
        qs = DeviceVersionAttribute.objects.filter(q)
        self.assertEqual(qs.count(), 1)

        helper1 = DeviceSelectionRule('os_version:eq:1.2')
        q = helper1.q()
        qs = DeviceVersionAttribute.objects.filter(q)
        self.assertEqual(qs.count(), 2)

        helper1 = DeviceSelectionRule('os_version:lt:1.1')
        q = helper1.q()
        qs = DeviceVersionAttribute.objects.filter(q)
        self.assertEqual(qs.count(), 1)

        helper1 = DeviceSelectionRule('os_version:lte:1.1')
        q = helper1.q()
        qs = DeviceVersionAttribute.objects.filter(q)
        self.assertEqual(qs.count(), 2)

        helper1 = DeviceSelectionRule('os_version:lt:2.0')
        q = helper1.q()
        qs = DeviceVersionAttribute.objects.filter(q)
        self.assertEqual(qs.count(), 4)

        helper1 = DeviceSelectionRule('os_version:lte:2.0')
        q = helper1.q()
        qs = DeviceVersionAttribute.objects.filter(q)
        self.assertEqual(qs.count(), 5)

        helper1 = DeviceSelectionRule('os_version:gte:2.0')
        q = helper1.q()
        qs = DeviceVersionAttribute.objects.filter(q)
        self.assertEqual(qs.count(), 1)

        helper1 = DeviceSelectionRule('os_version:gt:2.0')
        q = helper1.q()
        qs = DeviceVersionAttribute.objects.filter(q)
        self.assertEqual(qs.count(), 0)

    def testSelectionHelper(self):
        pd3 = Device.objects.create_device(project=self.p1, label='d3',
                                           template=self.dt1, created_by=self.u1, claimed_by=self.u2)
        pd4 = Device.objects.create_device(project=self.p1, label='d4',
                                           template=self.dt2, created_by=self.u1, claimed_by=self.u2)

        script1 = DeviceScript.objects.create(
            name='script 1',
            org=self.o1,
            major_version=2, minor_version=4, patch_version=0,
            created_by=self.u1,
            released=True,
        )
        fleet1 = Fleet.objects.create(name='F1', org=self.o2, created_by=self.u2)
        fleet1.register_device(self.pd1)
        fleet1.register_device(pd3)

        request1 = DeploymentRequest.objects.create(
            script=script1,
            org=self.o1,
            fleet=fleet1,
            released_on=timezone.now(),
            selection_criteria=['os_tag:eq:1024']
        )
        request2 = DeploymentRequest.objects.create(
            script=script1,
            org=self.o1,
            released_on=timezone.now(),
            selection_criteria=['os_tag:eq:1025']
        )
        self.assertEqual(self.dt1.org, self.o1)
        self.assertEqual(self.dt1.org, request2.org)

        helper1 = DeploymentDeviceSelectionHelper(request1)
        helper2 = DeploymentDeviceSelectionHelper(request2)

        self.assertEqual(helper1._base_device_qs().count(), 2)
        self.assertEqual(helper2._base_device_qs().count(), 4)

        for device in Device.objects.all():
            DeviceVersionAttribute.objects.create(
                device=device, type='os', tag=device.template.os_tag,
                major_version=0, minor_version=1
            )

        self.assertEqual(helper1._filter_by_criteria(helper1._base_device_qs()).count(), 2)
        self.assertEqual(helper2._filter_by_criteria(helper2._base_device_qs()).count(), 1)


