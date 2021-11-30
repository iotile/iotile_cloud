import datetime
import json
import struct

import dateutil.parser

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.physicaldevice.models import Device
from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()


class DeviceKeyDownloadableTestCase(TestMixin, APITestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        DeviceKey.objects.all().delete()
        Device.objects.all().delete()
        self.orgTestTearDown()
        self.userTestTearDown()
        self.deviceTemplateTestTearDown()

    def testDeviceGetKeyApi(self):
        pd1 = Device.objects.create(id=1, project=self.p1, template=self.dt1, created_by=self.u2)
        key1 = DeviceKey.objects.create_device(slug=pd1.slug, type='SSH', downloadable=True,
                                               secret='abc1', created_by=self.u1)
        key2 = DeviceKey.objects.create_device(slug=pd1.slug, type='USR', downloadable=False,
                                               secret='abc2', created_by=self.u1)

        url_allow = reverse('device-key', kwargs={'slug': pd1.slug})+'?type=ssh'
        url_forbidden = reverse('device-key', kwargs={'slug': pd1.slug})+'?type=usr'

        resp = self.client.get(url_allow, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url_forbidden, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.get(url_allow, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['key'], key1.secret)

        self.client.logout()
        ok = self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(url_forbidden, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.get(url_allow, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['key'], key1.secret)

        self.client.logout()
        ok = self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.get(url_forbidden, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.get(url_allow, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testCreateApi(self):
        pd1 = Device.objects.create(id=1, project=self.p1, template=self.dt1, created_by=self.u2)

        self.assertEqual(DeviceKey.objects.count(), 0)

        url = reverse('key-list')

        payload = {
            'slug': pd1.slug,
            'type': 'SSH',
            'secret': 'abc123'
        }

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        self.client.login(email='user1@foo.com', password='pass')

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DeviceKey.objects.count(), 1)
        key = DeviceKey.objects.first()
        self.assertFalse(key.downloadable)

        self.client.logout()

    def testIllegalCreateApi(self):
        pd1 = Device.objects.create(id=1, project=self.p1, template=self.dt1, created_by=self.u2)

        self.assertEqual(DeviceKey.objects.count(), 0)

        url = reverse('key-list')

        self.client.login(email='user1@foo.com', password='pass')

        # No slug
        payload = {
            'type': 'SSH',
            'secret': 'abc123'
        }

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # No slug
        payload = {
            'slug': pd1.slug,
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.logout()

    def testNoGetApi(self):
        pd1 = Device.objects.create(id=1, project=self.p1, template=self.dt1, created_by=self.u2)

        self.assertEqual(DeviceKey.objects.count(), 0)

        url_list = reverse('key-list')
        url_detail = url_list + pd1.slug + '/'

        self.client.login(email='user1@foo.com', password='pass')

        resp = self.client.get(url_list, format='json')
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        resp = self.client.get(url_detail, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()
