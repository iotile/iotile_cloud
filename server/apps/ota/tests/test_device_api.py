import datetime
import json

import dateutil.parser

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.devicescript.models import DeviceScript
from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()


class DeploymentDeviceInfoTests(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

        self.create_basic_test_devices()
        self.script1 = DeviceScript.objects.create(
            name='script 1',
            org=self.o1,
            major_version=2, minor_version=4, patch_version=0,
            created_by=self.u1,
            released=True,
        )
        self.fleet1 = Fleet.objects.create(name='F1', org=self.o2, created_by=self.u2)
        self.fleet1.register_device(self.pd1)
        self.pd3 = Device.objects.create_device(project=self.p1, sg=self.pd1.sg, label='d3',
                                                template=self.dt1, created_by=self.u2)
        self.fleet1.register_device(self.pd3)

        self.request1 = DeploymentRequest.objects.create(
            script=self.script1,
            org=self.o1,
            fleet=self.fleet1,
            released_on=timezone.now(),
            selection_criteria=['os_tag:gte:55']
        )
        self.request2 = DeploymentRequest.objects.create(
            script=self.script1,
            org=self.o2,
            released_on=timezone.now(),
            selection_criteria=['os_tag:gte:45']
        )
        self.action1 = DeploymentAction.objects.create(
            deployment=self.request1,
            device=self.pd1
        )
        self.action2 = DeploymentAction.objects.create(
            deployment=self.request2,
            device=self.pd2
        )

    def tearDown(self):
        DeviceScript.objects.all().delete()
        DeploymentRequest.objects.all().delete()
        DeploymentAction.objects.all().delete()
        DeviceVersionAttribute.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testAccess(self):

        url = reverse('api-ota-device', kwargs={'slug': self.pd1.slug})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.pd1.slug)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.pd1.has_access(self.u2))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.pd1.slug)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertFalse(self.pd1.has_access(self.u3))

        # No access to deployment for fleet on other org
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testGet(self):

        url = reverse('api-ota-device', kwargs={'slug': self.pd1.slug})

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.pd1.has_access(self.u2))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.pd1.slug)
        self.assertEqual(len(deserialized['deployments']), 2)
        self.assertEqual(len(deserialized['actions']), 1)

        self.client.logout()
