import datetime
import json

import dateutil.parser

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from rest_framework import status
from rest_framework.reverse import reverse

from apps.devicescript.models import DeviceScript
from apps.utils.test_util import TestMixin

from ..forms import DeploymentRequestForm
from ..models import *
from ..utils.selection import DeploymentDeviceSelectionHelper

user_model = get_user_model()


class DeploymentRequestTests(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

        self.d1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u1)
        self.fleet1 = Fleet.objects.create(name='F2', org=self.o2, created_by=self.u1)
        self.fleet1.register_device(self.d1)

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

    def testBasic(self):
        ds1 = DeviceScript.objects.create(
            name='script 2',
            org=self.o1,
            major_version=3, minor_version=4, patch_version=0,
            created_by=self.u1,
            released=True,
        )
        obj = DeploymentRequest.objects.create(
            script=ds1,
            org=self.o1,
            selection_criteria=['os_tag:gte:55']
        )
        self.assertIsNotNone(obj)
        self.assertEqual(str(obj), 'DeploymentReq-{0}'.format(obj.id))

        self.assertFalse(obj.completed)
        obj.completed_on = timezone.now()
        self.assertTrue(obj.completed)

    def testCreateForm(self):
        ds2 = DeviceScript.objects.create(
            name='script 2',
            org=self.o2,
            major_version=3, minor_version=4, patch_version=0,
            created_by=self.u1,
            released=True,
        )
        ota_create_url = reverse('ota:request-create', kwargs={'org_slug': self.o2.slug})
        ota_list_url = reverse('ota:request-list', kwargs={'org_slug': self.o2.slug})
        response = self.client.get(ota_create_url)
        self.assertRedirects(response, expected_url='/account/login/?next={}'.format(ota_create_url))

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertEqual(ok, True)

        response = self.client.get(ota_create_url, follow=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self.o2.has_access(self.u1))

        payload = {
            'script': ds2.id,
            'fleet': self.fleet1.id,
            'selection_criteria_text': 'os_tag:eq:55',
        }
        response = self.client.post(ota_create_url, payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertTrue(response.url.startswith(ota_list_url))
        self.assertEqual(DeploymentRequest.objects.count(), 1)

    def testCreateFormSelectionCriteriaNegative(self):
        ds2 = DeviceScript.objects.create(
            name='script 2',
            org=self.o2,
            major_version=3, minor_version=4, patch_version=0,
            created_by=self.u1,
            released=True,
        )
        ota_create_url = reverse('ota:request-create', kwargs={'org_slug': self.o2.slug})
        ota_list_url = reverse('ota:request-list', kwargs={'org_slug': self.o2.slug})
        response = self.client.get(ota_create_url)
        self.assertRedirects(response, expected_url='/account/login/?next={}'.format(ota_create_url))

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertEqual(ok, True)

        # No selection_criteria
        payload = {
            'script': ds2.id,
            'fleet': self.fleet1.id,
        }
        response = self.client.post(ota_create_url, payload)
        #data = response.content.decode("utf-8")
        self.assertContains(response, 'Please enter at least one selection criteria',
                            status_code=status.HTTP_200_OK)
        self.assertEqual(DeploymentRequest.objects.count(), 0)

        # Invalid type
        payload = {
            'script': ds2.id,
            'fleet': self.fleet1.id,
            'selection_criteria_text': 'invalid:gte:55',
        }
        response = self.client.post(ota_create_url, payload)
        self.assertContains(response, 'Type (invalid) is not valid input',
                            status_code=status.HTTP_200_OK)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(DeploymentRequest.objects.count(), 0)

        # Invalid op
        payload = {
            'script': ds2.id,
            'fleet': self.fleet1.id,
            'selection_criteria_text': 'os_tag:invalid:55',
        }
        response = self.client.post(ota_create_url, payload)
        self.assertContains(response, 'Op (invalid) is not valid input',
                            status_code=status.HTTP_200_OK)
        self.assertEqual(DeploymentRequest.objects.count(), 0)

        # Invalid value
        payload = {
            'script': ds2.id,
            'fleet': self.fleet1.id,
            'selection_criteria_text': 'os_tag:eq:invalid',
        }
        response = self.client.post(ota_create_url, payload)
        self.assertContains(response, 'Value (invalid) is not valid input for type (os_tag)',
                            status_code=status.HTTP_200_OK)
        self.assertEqual(DeploymentRequest.objects.count(), 0)

        # Multiple criteria, one invalid
        payload = {
            'script': ds2.id,
            'fleet': self.fleet1.id,
            'selection_criteria_text': 'os_tag:eq:12\nos_version:eq:invalid\nos_tag:eq:5054',
        }
        response = self.client.post(ota_create_url, payload)
        self.assertContains(response, 'Value (invalid) is not valid input for type (os_version)',
                            status_code=status.HTTP_200_OK)
        self.assertEqual(DeploymentRequest.objects.count(), 0)

        # End with a success
        payload = {
            'script': ds2.id,
            'fleet': self.fleet1.id,
            'selection_criteria_text': 'os_tag:eq:55',
        }
        response = self.client.post(ota_create_url, payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertTrue(response.url.startswith(ota_list_url))
        self.assertEqual(DeploymentRequest.objects.count(), 1)
