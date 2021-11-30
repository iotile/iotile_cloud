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


class DeploymentActionTests(TestMixin, APITestCase):

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

    def testGetListActions(self):
        url = reverse('deploymentaction-list')

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        resp = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        resp = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        resp = self.client.get(url+'?request={}'.format(self.request1.id), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url+'?request={}'.format(self.request1.id), format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testGetDetailAction(self):

        url = reverse('deploymentaction-detail', kwargs={'pk': self.action1.id})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], self.action1.id)

        resp = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], self.action1.id)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.o2.is_member(self.u2))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], self.action1.id)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        # No access to deployment for fleet on other org
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # All users can access deployment to Vendor
        url = reverse('deploymentaction-detail', kwargs={'pk': self.action2.id})
        self.assertFalse(self.o2.has_access(self.u3))
        self.assertFalse(self.request2.has_access(self.u3))
        self.assertFalse(self.action2.has_access(self.u3))
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        pd4 = Device.objects.create_device(project=self.p2, sg=self.pd2.sg, label='d4',
                                           template=self.dt1, created_by=self.u3)
        request_o3 = DeploymentRequest.objects.create(
            script=self.script1,
            org=self.o3,
            selection_criteria=['os_tag:gte:45']
        )

        action3 = DeploymentAction.objects.create(
            deployment=request_o3,
            device=pd4
        )

        self.assertTrue(self.o3.is_member(self.u3))
        self.assertTrue(request_o3.has_access(self.u3))
        self.assertTrue(action3.has_access(self.u3))

        # All users can access deployments from their own orgs
        url = reverse('deploymentaction-detail', kwargs={'pk': action3.id})
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], action3.id)

        self.client.logout()

    def testPostDeploymentAction(self):
        """
        Ensure we can create a new Deployment Action.
        """
        url = reverse('deploymentaction-list')
        data = {
            'deployment':self.request1.id,
            'device': self.pd1.slug,
            'last_attempt_on': '2018-01-08T10:00:00Z',
            'attempt_successful': 'false'
        }
        DeploymentAction.objects.all().delete()
        self.assertEqual(DeploymentAction.objects.count(), 0)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['deployment'], self.request1.id)
        self.assertEqual(deserialized['device'], self.pd1.slug)
        self.assertEqual(deserialized['last_attempt_on'], '2018-01-08T10:00:00Z')
        self.assertEqual(deserialized['attempt_successful'], False)
        self.assertEqual(deserialized['device_confirmation'], False)
        self.assertEqual(deserialized['log'], None)
        self.assertEqual(DeploymentAction.objects.count(), 1)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        data['last_attempt_on'] = '2018-01-09T11:00:00Z'
        data['attempt_successful'] = 'true'
        data['log'] = 'This is a test\nA test'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['deployment'], self.request1.id)
        self.assertEqual(deserialized['device'], self.pd1.slug)
        self.assertEqual(deserialized['last_attempt_on'], '2018-01-09T11:00:00Z')
        self.assertEqual(deserialized['attempt_successful'], True)
        self.assertEqual(deserialized['log'], 'This is a test\nA test')
        self.assertEqual(DeploymentAction.objects.count(), 2)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        request_o3 = DeploymentRequest.objects.create(
            script=self.script1,
            org=self.o3,
            selection_criteria=['os_tag:gte:45']
        )

        data = {
            'deployment':request_o3.id,
            'device': self.pd1.slug
        }
        self.assertTrue(request_o3.has_access(self.u3))
        self.assertFalse(self.pd1.has_access(self.u3))
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testDeleteDeploymentAction(self):
        """
        Ensure delete operations are protected
        """
        url1 = reverse('deploymentaction-detail', kwargs={'pk': self.action1.id})

        self.assertEqual(DeploymentAction.objects.count(), 2)
        resp = self.client.delete(url1)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.delete(url1)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(DeploymentAction.objects.count(), 2)

        resp = self.client.delete(url1+'?staff=1')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.delete(url1)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(DeploymentAction.objects.count(), 2)

        resp = self.client.delete(url1+'?staff=1')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(DeploymentAction.objects.count(), 1)

        self.client.logout()
