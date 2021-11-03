import json
from django.test import TestCase
from django.contrib.auth import get_user_model

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin
from apps.utils.utest.devices import TripDeviceMock
from apps.org.models import Org
from apps.project.models import Project
from apps.physicaldevice.models import Device
from apps.streamer.models import Streamer

from ..forms import SxdDeviceForm
from ..utils.trip import set_device_to_active

user_model = get_user_model()


class TripStartEndTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()

        self.device_mock = TripDeviceMock()

        self.o2 = Org.objects.get(slug='user-org')
        self.o2.register_user(self.u2, role='a1')

        self.p1 = Project.objects.get(name='Project 1')
        self.pd1 = self.p1.devices.first()

    def tearDown(self):
        self.device_mock.tearDown()
        self.userTestTearDown()

    def testStartTrip(self):
        self.pd1.state = 'N0'
        self.pd1.save()

        set_device_to_active(self.pd1, self.u2)
        self.assertEqual(self.pd1.state, 'N1')

    def testUploadResetTrip(self):
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)
        # Set up an external id for this device
        Device.objects.filter(pk=self.pd1.pk).update(external_id='test')
        self.pd1.refresh_from_db()

        # Set up streamers for this device
        streamer = Streamer.objects.create(device=self.pd1,
                                           index=0,
                                           last_id=11,
                                           created_by=self.u2)
        # Create 2 streamers to check if this still works
        Streamer.objects.create(device=self.pd1,
                                           index=1,
                                           last_id=11,
                                           created_by=self.u2)
        # Try to reset those two streamers
        data = {'reset':True, 'external_id':self.pd1.external_id}
        url = reverse('shipping:sxd-step-device', kwargs={'slug': self.p1.slug})
        response = self.client.post(url, data=data)
        streamer.refresh_from_db()
        self.assertEqual(streamer.last_id, 0)

        # Check that this streamer isn't reset
        streamer2 = Streamer.objects.create(device=self.pd1,
                                           index=2,
                                           last_id=12,
                                           created_by=self.u2)
        data = {'reset':False, 'external_id':self.pd1.external_id}
        response = self.client.post(url, data=data)
        streamer2.refresh_from_db()
        self.assertEqual(streamer2.last_id, 12)

class APITripStartEndTestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()

        self.device_mock = TripDeviceMock()

        self.o2 = Org.objects.get(slug='user-org')
        self.o2.register_user(self.u2, role='a1')

        self.p1 = Project.objects.get(name='Project 1')
        self.pd1 = self.p1.devices.first()

    def tearDown(self):
        self.device_mock.tearDown()
        self.userTestTearDown()

    def test_trip_setup(self):
        """
        Test API to start trip
        """
        url = reverse('shipping-trip-setup', kwargs={'slug': self.pd1.slug})
        payload = {}

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        self.pd1.state = 'N1'
        self.pd1.save()

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        self.pd1.state = 'N0'
        self.pd1.save()

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.pd1.slug)
        self.assertEqual(deserialized['label'], 'Arch Systems [Order# 123-abc]')
        self.assertEqual(deserialized['state'], 'N1')
        self.assertFalse(deserialized['busy'])
        device = Device.objects.get(slug=self.pd1.slug)
        self.assertFalse(device.busy)
        self.assertEqual(device.state, 'N1')
        self.assertEqual(device.label, 'Arch Systems [Order# 123-abc]')

        self.client.logout()

        self.pd1.state = 'N0'
        self.pd1.save()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.pd1.org.register_user(self.u3, role='m1')
        self.assertTrue(self.pd1.org.has_permission(self.u3, 'can_modify_device'))
        self.assertFalse(self.pd1.org.has_permission(self.u3, 'can_manage_org_and_projects'))

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)


        self.client.logout()

    def test_end_trip(self):
        """
        Test API to end trip
        """
        url = reverse('shipping-trip-archive', kwargs={'slug': self.pd1.slug})
        payload = {
            'title': 'This is a new archive',
        }

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        self.pd1.state = 'N0'
        self.pd1.save()
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        self.pd1.state = 'N1'
        self.pd1.save()
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['block'], 1)
        self.assertEqual(deserialized['title'], 'This is a new archive')
        self.assertEqual(deserialized['description'], '')
        self.assertEqual(deserialized['pid'], 'pid:000000')
        self.assertEqual(deserialized['device'], self.pd1.slug)
        device = Device.objects.get(slug=self.pd1.slug)
        self.assertFalse(device.busy)
        self.assertEqual(device.state, 'N0')
        self.assertEqual(device.label, 'Device [{}]'.format(device.slug))

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()
