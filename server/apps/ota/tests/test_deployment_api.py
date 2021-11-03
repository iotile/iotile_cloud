import json
import datetime
import dateutil.parser
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin

from apps.devicescript.models import DeviceScript
from ..models import *

user_model = get_user_model()


class DeploymentRequestTests(TestMixin, APITestCase):

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
        self.fleet1.org.set_permission(self.u2, 'can_manage_ota', True)

        self.request1 = DeploymentRequest.objects.create(
            script=self.script1,
            org=self.o1,
            fleet=self.fleet1,
            released_on=timezone.now(),
            selection_criteria=['os_tag:eq:1024']
        )
        self.request2 = DeploymentRequest.objects.create(
            script=self.script1,
            org=self.o1,
            released_on=timezone.now(),
            selection_criteria=['os_tag:eq:1025']
        )

    def tearDown(self):
        DeviceScript.objects.all().delete()
        DeploymentRequest.objects.all().delete()
        DeviceVersionAttribute.objects.all().delete()
        Device.objects.all().delete()
        Fleet.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testGetList(self):
        url = reverse('deploymentrequest-list')

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

        resp = self.client.get(url+'?fleet={}'.format(self.fleet1.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url+'?fleet={}'.format(self.fleet1.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testGetFilters(self):
        request3 = DeploymentRequest.objects.create(
            script=self.script1,
            org=self.o2,
            released_on=timezone.now(),
            fleet=self.fleet1,
            selection_criteria=['os_tag:gte:55']
        )
        request4 = DeploymentRequest.objects.create(
            script=self.script1,
            org=self.o2,
            fleet=self.fleet1,
            selection_criteria=['os_tag:gte:55']
        )
        request5 = DeploymentRequest.objects.create(
            script=self.script1,
            org=self.o2,
            released_on=timezone.now(),
            completed_on=timezone.now(),
            fleet=self.fleet1,
            selection_criteria=['os_tag:gte:55']
        )
        request6 = DeploymentRequest.objects.create(
            script=self.script1,
            org=self.o2,
            released_on=timezone.now(),
            selection_criteria=['os_tag:gte:45']
        )
        fleet2 = Fleet.objects.create(name='F2', org=self.o2, created_by=self.u2)
        request7 = DeploymentRequest.objects.create(
            script=self.script1,
            org=self.o2,
            fleet=fleet2,
            released_on=timezone.now(),
            selection_criteria=['os_tag:gte:45']
        )

        url = reverse('deploymentrequest-list')

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url+'?fleet=foobar', format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.get(url+'?fleet={}'.format(self.fleet1.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)
        self.assertTrue(deserialized['results'][0]['id'] in [self.request1.id, request3.id])
        self.assertTrue(deserialized['results'][1]['id'] in [self.request1.id, request3.id])

        # Test list of fleets
        resp = self.client.get(url+'?fleet={0},{1}'.format(self.fleet1.slug, fleet2.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 3)

        resp = self.client.get(url+'?org=foobar', format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.get(url+'?org={}'.format(self.o2.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 3)
        self.assertTrue(deserialized['results'][0]['id'] in [request3.id, request6.id, request7.id])
        self.assertTrue(deserialized['results'][1]['id'] in [request3.id, request6.id, request7.id])
        self.assertTrue(deserialized['results'][2]['id'] in [request3.id, request6.id, request7.id])

        resp = self.client.get(url+'?org={0},{1}'.format(self.o1.slug, self.o2.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 5)

        resp = self.client.get(url+'?scope=foobar', format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.get(url+'?scope={}'.format(self.fleet1.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)
        expected_ids = [
            self.request1.id, # Vendor deployment to customer fleet
            self.request2.id, # Vendor deployment (global)
            request3.id,      # Org deployment to custom fleet
            request6.id,      # Org deployment
        ]
        self.assertTrue(deserialized['results'][0]['id'] in expected_ids)
        self.assertTrue(deserialized['results'][1]['id'] in expected_ids)
        self.assertTrue(deserialized['results'][2]['id'] in expected_ids)
        self.assertTrue(deserialized['results'][3]['id'] in expected_ids)

        resp = self.client.get(url+'?scope={}'.format(self.o2.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        expected_ids = [
            self.request1.id, # Vendor deployment to customer fleet
            self.request2.id, # Vendor deployment (global)
            request3.id,      # Org deployment to custom fleet1
            request7.id,      # Org deployment to custom fleet2
            request6.id,      # Org deployment
        ]
        self.assertEqual(deserialized['count'], 5)
        self.assertTrue(deserialized['results'][0]['id'] in expected_ids)
        self.assertTrue(deserialized['results'][1]['id'] in expected_ids)
        self.assertTrue(deserialized['results'][2]['id'] in expected_ids)
        self.assertTrue(deserialized['results'][3]['id'] in expected_ids)

        resp = self.client.get(url+'?scope=global', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertTrue(deserialized['results'][0]['id'] in [self.request2.id])

        self.client.logout()

    def testGetDetail(self):

        url = reverse('deploymentrequest-detail', kwargs={'pk': self.request1.id})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], self.request1.id)

        resp = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], self.request1.id)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.o2.is_member(self.u2))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], self.request1.id)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        # No access to deployment for fleet on other org
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # All users can access deployment to Vendor
        url = reverse('deploymentrequest-detail', kwargs={'pk': self.request2.id})
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], self.request2.id)

        request_o3 = DeploymentRequest.objects.create(
            script=self.script1,
            org=self.o3,
            selection_criteria=['os_tag:gte:45']
        )
        self.assertTrue(self.o3.is_member(self.u3))

        # All users can access deployments from their own orgs
        url = reverse('deploymentrequest-detail', kwargs={'pk': request_o3.id})
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], request_o3.id)

        self.client.logout()

    def testPostDeploymentRequest(self):
        """
        Ensure we can create a new Deployment Action.
        """
        url = reverse('deploymentrequest-list')
        data = {
            'script':self.script1.slug,
            'org': self.o1.slug,
            'released_on': timezone.now()
        }
        DeploymentRequest.objects.all().delete()
        self.assertEqual(DeploymentRequest.objects.count(), 0)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['script'], self.script1.slug)
        self.assertEqual(deserialized['org'], self.o1.slug)
        self.assertEqual(DeploymentRequest.objects.count(), 1)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        data = {
            'script':self.script1.slug,
            'org': self.o2.slug,
            'released_on': timezone.now()
        }
        self.assertFalse(self.o1.has_permission(self.u2, 'can_manage_ota'))
        self.assertTrue(self.o2.has_permission(self.u2, 'can_manage_ota'))
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['org'], self.o2.slug)
        self.assertEqual(DeploymentRequest.objects.count(), 2)

        data = {
            'script':self.script1.slug,
            'org': self.o2.slug,
            'fleet': self.fleet1.slug,
            'released_on': timezone.now()
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['org'], self.o2.slug)
        self.assertEqual(deserialized['fleet'], self.fleet1.slug)
        self.assertEqual(DeploymentRequest.objects.count(), 3)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        data = {
            'script':self.script1.slug,
            'org': self.o2.slug,
            'released_on': timezone.now()
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        data = {
            'script':self.script1.slug,
            'org': self.o3.slug,
            'fleet': self.fleet1.slug,
            'released_on': timezone.now()
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        membership = self.p1.org.register_user(self.u3, role='m1')
        membership.permissions['can_manage_ota'] = False
        membership.save()

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testDeleteDeploymentRequest(self):
        """
        Ensure delete operations are protected
        """
        url1 = reverse('deploymentrequest-detail', kwargs={'pk': self.request1.id})
        url2 = reverse('deploymentrequest-detail', kwargs={'pk': self.request2.id})

        self.assertEqual(DeploymentRequest.objects.count(), 2)
        resp = self.client.delete(url1)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        self.assertFalse(self.o1.has_permission(self.u2, 'can_manage_ota'))
        self.assertTrue(self.fleet1.org.has_permission(self.u2, 'can_manage_ota'))

        resp = self.client.delete(url1)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(DeploymentRequest.objects.count(), 1)

        resp = self.client.delete(url2)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(DeploymentRequest.objects.count(), 1)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.delete(url2)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(DeploymentRequest.objects.count(), 0)

        self.client.logout()

    def testGetDeviceListPerDeployment(self):
        pd3 = Device.objects.create_device(project=self.p1, label='d3', active=True,
                                           template=self.dt1, created_by=self.u1, claimed_by=self.u2)
        pd4 = Device.objects.create_device(project=self.p1, label='d4', active=True,
                                           template=self.dt2, created_by=self.u1, claimed_by=self.u2)

        for device in Device.objects.all():
            DeviceVersionAttribute.objects.create(
                device=device, type='os', tag=device.template.os_tag,
                major_version=0, minor_version=1
            )

        url1 = reverse('deploymentrequest-devices', kwargs={'pk': self.request1.id})
        url2 = reverse('deploymentrequest-devices', kwargs={'pk': self.request2.id})

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        resp = self.client.get(url2, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()
