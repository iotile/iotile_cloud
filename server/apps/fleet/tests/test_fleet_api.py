import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()


class FleetAPITests(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.d1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.d2 = Device.objects.create_device(project=self.p1, label='d2', template=self.dt1, created_by=self.u2)
        self.d3 = Device.objects.create_device(project=self.p2, label='d3', template=self.dt1, created_by=self.u3)
        self.o2.set_permission(self.u2, 'can_manage_ota', True)

    def tearDown(self):
        FleetMembership.objects.all().delete()
        Fleet.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testPostFleet(self):
        """
        Ensure we can create a new Org object.
        """
        url = reverse('fleet-list')
        data = {'name':'Fleet 1', 'org': self.o2.slug}

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Don't accept duplicate names
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['non_field_errors'], ['The fields org, name must make a unique set.'])

        self.client.logout()

    def testGetFleet(self):
        url = reverse('fleet-list')

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        f1 = Fleet.objects.create(name='F1', org=self.o2, created_by=self.u2)
        f2 = Fleet.objects.create(name='F2', org=self.o3, created_by=self.u3)
        detail_url = reverse('fleet-detail', kwargs={'slug': str(f1.slug)})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        resp = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.get(detail_url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], f1.id)
        self.assertEqual(deserialized['name'], str(f1.name))
        self.assertEqual(deserialized['slug'], str(f1.slug))

        self.client.logout()

        # Staff has access to all
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], f1.id)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        detail_url = reverse('fleet-detail', kwargs={'slug': str(f2.slug)})
        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testGetFleetMembership(self):
        f1 = Fleet.objects.create(name='F1', org=self.o2, created_by=self.u2)
        f2 = Fleet.objects.create(name='F2', org=self.o3, created_by=self.u3)
        self.assertEqual(Fleet.objects.count(), 2)
        f1.register_device(self.d1)
        f1.register_device(self.d2)
        f2.register_device(self.d3)

        detail_url = reverse('fleet-devices', kwargs={'slug': str(f1.slug)})

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(detail_url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def testPostFleetRegister(self):
        f1 = Fleet.objects.create(name='F1', org=self.o2, created_by=self.u2)
        f2 = Fleet.objects.create(name='F2', org=self.o3, created_by=self.u3)

        detail_url = reverse('fleet-register', kwargs={'slug': str(f1.slug)})
        payload = {
            'device': self.d1.slug
        }

        resp = self.client.post(detail_url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(detail_url+'?staff=1', data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            'device': self.d2.slug
        }

        resp = self.client.post(detail_url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        d4 = Device.objects.create_device(project=self.p1, label='d4', template=self.dt1, created_by=self.u2)

        payload = {
            'device': d4.slug
        }

        resp = self.client.post(detail_url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

    def testPostFleetDeregister(self):
        f1 = Fleet.objects.create(name='F1', org=self.o2, created_by=self.u2)
        FleetMembership.objects.create(device=self.d1, fleet=f1)
        FleetMembership.objects.create(device=self.d2, fleet=f1)

        self.assertEqual(f1.members.count(), 2)

        detail_url = reverse('fleet-deregister', kwargs={'slug': str(f1.slug)})
        payload = {
            'device': self.d1.slug
        }

        resp = self.client.post(detail_url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(detail_url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(f1.members.all().count(), 1)

        self.client.logout()

    def testPostFleetMembershipIntegrity(self):
        f1 = Fleet.objects.create(name='F1', org=self.o2, created_by=self.u2)

        detail_url = reverse('fleet-register', kwargs={'slug': str(f1.slug)})
        payload = {
            'device': self.d1.slug
        }

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(detail_url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        resp = self.client.post(detail_url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.logout()

    def testDeviceFilter(self):
        detail_url = reverse('fleet-list')+'?device={}'.format(self.d1)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        f1 = Fleet.objects.create(name='F1', org=self.o2, created_by=self.u2, is_network=True)
        f2 = Fleet.objects.create(name='F2', org=self.o2, created_by=self.u2)
        self.assertEqual(Fleet.objects.count(), 2)
        f1.register_device(self.d1)
        f1.register_device(self.d2)
        f2.register_device(self.d2)
        # Hack to make d3 be in the same org
        self.d3.org = self.d2.org
        self.d3.save()
        f2.register_device(self.d3)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['slug'], f1.slug)

        detail_url = reverse('fleet-list')+'?device={}'.format(self.d2)
        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        detail_url = reverse('fleet-list')+'?device={}&is_network=1'.format(self.d2)
        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['slug'], f1.slug)

        detail_url = reverse('fleet-list')+'?device={}&is_network=0'.format(self.d2)
        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['slug'], f2.slug)

        self.client.logout()

    def testOrgFilter(self):
        detail_url = reverse('fleet-list')+'?org={}'.format(self.o1.slug)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        # Hack to make d2 and d3 be in o1
        self.d2.org = self.o1
        self.d3.org = self.o1
        self.d2.save()
        self.d3.save()
        f1 = Fleet.objects.create(name='F1', org=self.o2, created_by=self.u1, is_network=True)
        f2 = Fleet.objects.create(name='F2', org=self.o1, created_by=self.u1)
        self.assertEqual(Fleet.objects.count(), 2)
        f1.register_device(self.d1)
        f2.register_device(self.d2)
        f2.register_device(self.d3)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['slug'], f2.slug)

        detail_url = reverse('fleet-list')+'?staff=1&org={}&is_network=1'.format(self.o2.slug)
        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['slug'], f1.slug)

        self.client.logout()
