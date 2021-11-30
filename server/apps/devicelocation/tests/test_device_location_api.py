import datetime
import json

import dateutil.parser

from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.physicaldevice.models import Device
from apps.streamfilter.models import *
from apps.utils.data_mask.mask_utils import set_data_mask
from apps.utils.gid.convert import *
from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()


class DeviceLocationApiTestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)

    def tearDown(self):
        DeviceLocation.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasicGet(self):
        dt1 = dateutil.parser.parse('2017-09-28T10:00:00Z')
        dt2 = dateutil.parser.parse('2017-09-28T11:00:00Z')
        dt3 = dateutil.parser.parse('2017-09-30T10:00:00Z')
        dt4 = dateutil.parser.parse('2017-09-30T10:10:00Z')
        dt5 = dateutil.parser.parse('2017-09-30T10:20:00Z')
        l1 = DeviceLocation.objects.create(
            target_slug=self.pd1.slug, timestamp=dt1, lat=12.1234, lon=10.000, user=self.u2
        )
        DeviceLocation.objects.create(
            target_slug=self.pd1.slug, timestamp=dt2, lat=13.1234, lon=10.000, user=self.u2
        )
        DeviceLocation.objects.create(
            target_slug=self.pd1.slug, timestamp=dt3, lat=14.1234, lon=10.000, user=self.u2
        )
        DeviceLocation.objects.create(
            target_slug=self.pd1.slug, timestamp=dt4, lat=15.1234, lon=10.000, user=self.u2
        )
        DeviceLocation.objects.create(
            target_slug=self.pd1.slug, timestamp=dt5, lat=16.1234, lon=10.000, user=self.u2
        )
        l3 = DeviceLocation.objects.create(
            target_slug=self.pd2.slug, timestamp=timezone.now(), lat=17.1234, lon=10.000, user=self.u3
        )
        list_url = reverse('devicelocation-list')
        detail_url1 = reverse('devicelocation-detail', kwargs={'pk': l1.id})
        detail_url3 = reverse('devicelocation-detail', kwargs={'pk': l3.id})

        set_data_mask(self.pd1, '2017-09-28T10:30:00Z', '2017-09-30T10:15:00Z', [], [], self.u1)

        response = self.client.get(list_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.get(detail_url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(list_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(list_url+'?target={}'.format(self.pd1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 5)
        self.assertEqual(deserialized['results'][0]['lat'], '12.123400')

        response = self.client.get(list_url+'?target={}&mask=1'.format(self.pd1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)
        self.assertEqual(deserialized['results'][0]['lat'], '13.123400')

        response = self.client.get(list_url+'?target={}&mask=1'.format(self.pd1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)
        self.assertEqual(deserialized['results'][0]['lat'], '13.123400')

        url = list_url+'?target={0}&start={1}&end={2}'.format(self.pd1.slug, '2017-09-28T11:30:00Z', '2017-09-30T10:00:10Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['lat'], '14.123400')

        url = list_url+'?target={0}&start={1}&end={2}&mask=1'.format(self.pd1.slug, '2017-09-28T11:30:00Z', '2017-09-30T10:00:10Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['lat'], '14.123400')

        url = list_url+'?target={0}&start={1}&end={2}'.format(self.pd1.slug, '2017-08-28T11:00:00Z', '2017-10-30T10:00:10Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 5)
        self.assertEqual(deserialized['results'][0]['lat'], '12.123400')

        url = list_url+'?target={0}&start={1}&end={2}&mask=1'.format(self.pd1.slug, '2017-08-28T11:00:00Z', '2017-10-30T10:00:10Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)
        self.assertEqual(deserialized['results'][0]['lat'], '13.123400')

        response = self.client.get(detail_url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['lat'], '12.123400')
        self.assertEqual(deserialized['user'], self.u2.slug)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(list_url+'?target={}'.format(self.pd1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 5)
        response = self.client.get(detail_url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(list_url+'?target={}'.format(self.pd1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)
        response = self.client.get(list_url+'?target={}'.format(self.pd2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        response = self.client.get(detail_url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.get(detail_url3, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        membership = self.p1.org.register_user(self.u3, role='m1')
        membership.permissions['can_read_device_locations'] = False
        membership.save()

        response = self.client.get(list_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.get(list_url+'?target={}'.format(self.pd1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)
        response = self.client.get(detail_url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testBasicPost(self):
        url = reverse('devicelocation-list')
        payload = {
            'target': self.pd1.slug,
            'timestamp': timezone.now(),
            'lat': '12.123456',
            'lon': '13.123456'
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DeviceLocation.objects.count(), 1)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['target'], self.pd1.slug)
        pd1 = Device.objects.get(pk=self.pd1.id)
        self.assertEqual(str(pd1.lat), '12.123456')
        self.assertEqual(str(pd1.lon), '13.123456')

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            'target': self.pd1.slug,
            'timestamp': timezone.now(),
            'lat': '12.123456',
            'lon': '13.123456'
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DeviceLocation.objects.count(), 2)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['target'], self.pd1.slug)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        # Operators can still upload locations
        self.p1.org.register_user(self.u3, role='r1')

        payload = {
            'target': self.pd1.slug,
            'timestamp': timezone.now(),
            'lat': '12.123456',
            'lon': '13.123456'
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DeviceLocation.objects.count(), 3)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['target'], self.pd1.slug)

        self.client.logout()

    def testMultiPost(self):
        url = reverse('devicelocation-list')
        payload = [
            {
                'target': self.pd1.slug,
                'timestamp': timezone.now(),
                'lat': '12.123456',
                'lon': '13.123456'
            },
            {
                'target': self.pd1.slug,
                'timestamp': timezone.now(),
                'lat': '12.223456',
                'lon': '13.223456'
            }
        ]

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DeviceLocation.objects.count(), 2)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)
        pd1 = Device.objects.get(pk=self.pd1.id)
        self.assertEqual(str(pd1.lat), '12.223456')
        self.assertEqual(str(pd1.lon), '13.223456')

        # Illegal to post locations for multiple devices
        payload = [
            {
                'target': self.pd1.slug,
                'timestamp': timezone.now(),
                'lat': '12.123456',
                'lon': '13.123456'
            },
            {
                'target': self.pd2.slug,
                'timestamp': timezone.now(),
                'lat': '12.123456',
                'lon': '13.123456'
            }
        ]
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.logout()

        payload = [
            {
                'target': self.pd1.slug,
                'timestamp': timezone.now(),
                'lat': '12.123456',
                'lon': '13.123456'
            },
            {
                'target': self.pd1.slug,
                'timestamp': timezone.now(),
                'lat': '12.123456',
                'lon': '13.123456'
            }
        ]
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(deserialized['count'], 2)

        self.client.logout()

