import datetime
import json

import dateutil.parser

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.devicescript.models import DeviceScript
from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()


class DeploymentRequestTests(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

        self.create_basic_test_devices()

    def tearDown(self):
        DeviceScript.objects.all().delete()
        DeploymentRequest.objects.all().delete()
        DeploymentAction.objects.all().delete()
        DeviceVersionAttribute.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasic(self):
        ds1 = DeviceScript.objects.create(
            name='script 1',
            org=self.o1,
            major_version=2, minor_version=4, patch_version=0,
            created_by=self.u1,
            released=True,
        )
        req = DeploymentRequest.objects.create(
            script=ds1,
            org=self.o1,
            selection_criteria=['os_tag:gte:55']
        )
        obj = DeploymentAction.objects.create(
            deployment=req,
            device=self.pd1
        )
        self.assertIsNotNone(obj)
        self.assertEqual(str(obj), 'DeploymentAction-{0}'.format(obj.id))

