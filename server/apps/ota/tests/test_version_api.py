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
from apps.utils.timezone_utils import formatted_ts

from apps.devicescript.models import DeviceScript
from ..models import *

user_model = get_user_model()


class DeviceVersionAttributeTests(TestMixin, APITestCase):

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

    def testAccess(self):

        url = reverse('deviceversionattribute-list')

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
        self.assertTrue(self.pd1.has_access(self.u2))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertFalse(self.pd1.has_access(self.u3))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        resp = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        self.client.logout()

    def testPostDeviceVersion(self):

        url = reverse('deviceversionattribute-list')
        ts = timezone.now()
        data = {
            'device':self.pd1.slug,
            'type': 'os',
            'major_version': 1,
            'minor_version': 3,
            'tag': 1024,
            'streamer_local_id': 6567,
            'updated_ts': formatted_ts(ts)
        }
        DeviceVersionAttribute.objects.all().delete()
        self.assertEqual(DeviceVersionAttribute.objects.count(), 0)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(url+'?staff=1', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['device'], self.pd1.slug)
        self.assertEqual(deserialized['type'], 'os')
        self.assertEqual(deserialized['version'], 'v1.3')
        self.assertEqual(deserialized['tag'], 1024)
        self.assertEqual(deserialized['streamer_local_id'], 6567)
        self.assertEqual(deserialized['updated_ts'], formatted_ts(ts))
        self.assertEqual(DeviceVersionAttribute.objects.count(), 1)

        self.client.logout()

    def testDeleteDeviceVersion(self):
        """
        Ensure delete operations are protected
        """
        ver = DeviceVersionAttribute.objects.create(
            device=self.pd1,
            type='os',
            tag=5,
            major_version=3,
            minor_version=1
        )

        url1 = reverse('deviceversionattribute-detail', kwargs={'pk': ver.id})

        self.assertEqual(DeviceVersionAttribute.objects.count(), 3)
        resp = self.client.delete(url1)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.delete(url1)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(DeviceVersionAttribute.objects.count(), 3)

        resp = self.client.delete(url1+'?staff=1')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.delete(url1)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(DeviceVersionAttribute.objects.count(), 3)

        resp = self.client.delete(url1+'?staff=1')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(DeviceVersionAttribute.objects.count(), 2)

        self.client.logout()

    def testDeviceGetVersions(self):

        v3 = DeviceVersionAttribute.objects.create(
            device=self.pd1,
            type='sg',
            tag=1027,
            major_version=1,
            minor_version=0,
            streamer_local_id=6678,
            updated_ts=timezone.now()
        )
        url = reverse('device-versions', kwargs={'slug': self.pd1.slug})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(len(deserialized), 2)
        self.assertTrue(deserialized[0]['type'] != deserialized[1]['type'])
        self.assertTrue(deserialized[0]['type'] in ['sg', 'os'])
        self.assertTrue(deserialized[1]['type'] in ['sg', 'os'])

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(len(deserialized), 2)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testGetFilter(self):

        pd3 = Device.objects.create_device(id=1, project=self.p1, label='d3',
                                           template=self.dt1, created_by=self.u1, claimed_by=self.u2)
        v3 = DeviceVersionAttribute.objects.create(
            device=self.pd2,
            type='sg',
            tag=1027,
            major_version=1,
            minor_version=0,
            streamer_local_id=6000,
            updated_ts=timezone.now()
        )
        v4 = DeviceVersionAttribute.objects.create(
            device=self.pd1,
            type='sg',
            tag=1027,
            major_version=1,
            minor_version=0,
            streamer_local_id=6678,
            updated_ts=timezone.now()
        )
        v5 = DeviceVersionAttribute.objects.create(
            device=self.pd1,
            type='sg',
            tag=1027,
            major_version=2,
            minor_version=0,
            streamer_local_id=7678,
            updated_ts=timezone.now()
        )
        v6 = DeviceVersionAttribute.objects.create(
            device=pd3,
            type='sg',
            tag=1027,
            major_version=2,
            minor_version=0,
            streamer_local_id=7678,
            updated_ts=timezone.now()
        )

        url = reverse('deviceversionattribute-list')

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['version'], v3.version)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 5)

        resp = self.client.get(url+'?device={}'.format(pd3.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['version'], v6.version)

        resp = self.client.get(url+'?device={}'.format(self.pd1.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)

        resp = self.client.get(url+'?device={}&type=os'.format(self.pd1.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        resp = self.client.get(url+'?device={}&latest=True'.format(self.pd1.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)
        self.assertTrue(deserialized['results'][0]['type'] != deserialized['results'][1]['type'])
        self.assertTrue(deserialized['results'][0]['type'] in ['sg', 'os'])
        self.assertTrue(deserialized['results'][1]['type'] in ['sg', 'os'])

        self.client.logout()
