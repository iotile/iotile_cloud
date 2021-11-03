import datetime
import json

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.datablock.models import DataBlock
from apps.org.models import Org
from apps.project.models import Project
from apps.streamevent.models import StreamEventData
from apps.streamdata.models import StreamData
from apps.streamdata.serializers import StreamDataSerializer
from apps.utils.data_mask.mask_utils import set_data_mask
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import formatted_ts
from apps.utils.utest.devices import TripDeviceMock

user_model = get_user_model()


class APITripInfoTestCase(TestMixin, APITestCase):

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

    def testMock(self):
        self.device_mock.testMock(self)

    def test_inactive_trip(self):
        """
        Test API for Inactive Trip
        """
        url = reverse('shipping-trip-detail', kwargs={'slug': self.pd1.slug})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.pd1.slug)
        self.assertEqual(deserialized['label'], self.pd1.label)
        self.assertEqual(deserialized['state'], 'N0')
        self.assertIsNone(deserialized['data_mask'])

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.pd1.org.register_user(self.u3, role='m1')
        self.assertTrue(self.pd1.org.has_permission(self.u3, 'can_modify_device'))
        self.assertFalse(self.pd1.org.has_permission(self.u3, 'can_manage_org_and_projects'))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.pd1.org.de_register_user(self.u3, delete_obj=True)

        self.pd1.org.register_user(self.u3, role='r1')
        self.assertFalse(self.pd1.org.has_permission(self.u3, 'can_modify_device'))
        self.assertFalse(self.pd1.org.has_permission(self.u3, 'can_manage_org_and_projects'))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

    def test_active_trip(self):
        """
        Test API for Active Trip
        """
        setup_url = reverse('shipping-trip-setup', kwargs={'slug': self.pd1.slug})
        url = reverse('shipping-trip-detail', kwargs={'slug': self.pd1.slug})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        # Trip Setup
        self.pd1.state = 'N0'
        self.pd1.save()
        resp = self.client.post(setup_url, format='json', data={})
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.pd1 = self.p1.devices.first()
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.pd1.slug)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.pd1.org.register_user(self.u3, role='m1')
        self.assertTrue(self.pd1.org.has_permission(self.u3, 'can_modify_device'))
        self.assertFalse(self.pd1.org.has_permission(self.u3, 'can_manage_org_and_projects'))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.pd1.org.de_register_user(self.u3, delete_obj=True)

        self.pd1.org.register_user(self.u3, role='r1')
        self.assertFalse(self.pd1.org.has_permission(self.u3, 'can_modify_device'))
        self.assertFalse(self.pd1.org.has_permission(self.u3, 'can_manage_org_and_projects'))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

    def test_trip_mask(self):
        """
        Test API for Active Trip
        """
        setup_url = reverse('shipping-trip-setup', kwargs={'slug': self.pd1.slug})
        url = reverse('shipping-trip-detail', kwargs={'slug': self.pd1.slug})

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        # Trip Setup
        self.pd1.state = 'N0'
        self.pd1.save()
        resp = self.client.post(setup_url, format='json', data={})
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.pd1 = self.p1.devices.first()

        start = StreamData.objects.get(stream_slug=self.pd1.get_stream_slug_for('0e00'))
        end = StreamData.objects.get(stream_slug=self.pd1.get_stream_slug_for('0e01'))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.pd1.slug)
        self.assertEqual(deserialized['label'], self.pd1.label)
        self.assertEqual(deserialized['state'], 'N1')

        # There should be no Mask on data
        self.assertIsNone(deserialized['data_mask'])
        self.assertFalse(deserialized['trip_date_range']['masked'])

        # Original start / end and actual start / end should be equal
        self.assertEqual(deserialized['trip_date_range']['original_start'], formatted_ts(start.timestamp))
        self.assertEqual(deserialized['trip_date_range']['original_end'], formatted_ts(end.timestamp))
        self.assertEqual(deserialized['trip_date_range']['actual_start'], formatted_ts(start.timestamp))
        self.assertEqual(deserialized['trip_date_range']['actual_end'], formatted_ts(end.timestamp))

        # Start_data and end_data should hold data of TripStart and TripEnd events
        self.assertEqual(deserialized['trip_date_range']['start_data'], StreamDataSerializer(start).data)
        self.assertEqual(deserialized['trip_date_range']['end_data'], StreamDataSerializer(end).data)

        # Should be 5 streams
        self.assertEqual(len(deserialized['streams']), 5)

        # Valid mask on start date and no mask on end date
        mask_start = start.timestamp + datetime.timedelta(seconds=60)
        set_data_mask(self.pd1, formatted_ts(mask_start), None, [], [], self.u1)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.pd1.slug)
        self.assertEqual(deserialized['label'], self.pd1.label)
        self.assertEqual(deserialized['state'], 'N1')

        self.assertIsNotNone(deserialized['data_mask'])
        self.assertEqual(deserialized['data_mask']['start'], formatted_ts(mask_start))
        self.assertIsNone(deserialized['data_mask']['end'])

        self.assertTrue(deserialized['trip_date_range']['masked'])
        self.assertEqual(deserialized['trip_date_range']['original_start'], formatted_ts(start.timestamp))
        self.assertEqual(deserialized['trip_date_range']['original_end'], formatted_ts(end.timestamp))
        self.assertEqual(deserialized['trip_date_range']['actual_start'], formatted_ts(mask_start))
        self.assertEqual(deserialized['trip_date_range']['actual_end'], formatted_ts(end.timestamp))

        # Invalid mask on start date (older than actual start) and valid end mask
        mask_start = start.timestamp - datetime.timedelta(seconds=60)
        mask_end = end.timestamp - datetime.timedelta(seconds=60)
        set_data_mask(self.pd1, formatted_ts(mask_start), formatted_ts(mask_end), [], [], self.u1)
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.pd1.slug)
        self.assertEqual(deserialized['label'], self.pd1.label)
        self.assertEqual(deserialized['state'], 'N1')

        self.assertTrue(deserialized['trip_date_range']['masked'])
        self.assertEqual(deserialized['trip_date_range']['original_start'], formatted_ts(start.timestamp))
        self.assertEqual(deserialized['trip_date_range']['original_end'], formatted_ts(end.timestamp))
        self.assertEqual(deserialized['trip_date_range']['actual_start'], formatted_ts(start.timestamp))
        self.assertEqual(deserialized['trip_date_range']['actual_end'], formatted_ts(mask_end))

        self.assertIsNotNone(deserialized['data_mask'])
        self.assertEqual(deserialized['data_mask']['start'], formatted_ts(mask_start))
        self.assertEqual(deserialized['data_mask']['end'], formatted_ts(mask_end))

        self.client.logout()

    def test_trip_archive(self):
        """
        Test API for Active Trip
        """
        setup_url = reverse('shipping-trip-setup', kwargs={'slug': self.pd1.slug})
        archive_url = reverse('shipping-trip-archive', kwargs={'slug': self.pd1.slug})
        archive_payload = {
            'title': 'This is a new archive',
        }

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        # Trip Setup
        self.pd1.state = 'N0'
        self.pd1.save()
        resp = self.client.post(setup_url, format='json', data={})
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        # Trip Archive
        resp = self.client.post(archive_url, format='json', data=archive_payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(resp.content.decode())
        block_slug = deserialized['slug']

        block = DataBlock.objects.get(slug=block_slug)
        url = reverse('shipping-trip-detail', kwargs={'slug': block_slug})

        start = StreamData.objects.get(stream_slug=block.get_stream_slug_for('0e00'))
        end = StreamData.objects.get(stream_slug=block.get_stream_slug_for('0e01'))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], block.slug)
        self.assertEqual(deserialized['label'], block.title)
        self.assertEqual(deserialized['state'], 'A')
        self.assertIsNone(deserialized['data_mask'])
        self.assertEqual(deserialized['trip_date_range']['original_start'], formatted_ts(start.timestamp))
        self.assertEqual(deserialized['trip_date_range']['original_end'], formatted_ts(end.timestamp))
        self.assertEqual(deserialized['trip_date_range']['actual_start'], formatted_ts(start.timestamp))
        self.assertEqual(deserialized['trip_date_range']['actual_end'], formatted_ts(end.timestamp))
        self.assertFalse(deserialized['trip_date_range']['masked'])
        self.assertEqual(deserialized['trip_date_range']['start_data'], StreamDataSerializer(start).data)
        self.assertEqual(deserialized['trip_date_range']['end_data'], StreamDataSerializer(end).data)
        self.assertEqual(len(deserialized['streams']), 5)

        self.client.logout()

    def test_trip_info_saver(self):
        """
        To test a saver, remove the start/end signals
        """
        setup_url = reverse('shipping-trip-setup', kwargs={'slug': self.pd1.slug})
        archive_url = reverse('shipping-trip-archive', kwargs={'slug': self.pd1.slug})
        archive_payload = {
            'title': 'This is a new archive',
        }

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        # Trip Setup
        self.pd1.state = 'N0'
        self.pd1.save()
        resp = self.client.post(setup_url, format='json', data={})
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        # Delete 0e00 and 0e01 to emulate saver
        StreamData.objects.get(stream_slug=self.pd1.get_stream_slug_for('0e00')).delete()
        StreamData.objects.get(stream_slug=self.pd1.get_stream_slug_for('0e01')).delete()

        start_temp = StreamData.objects.filter(stream_slug=self.pd1.get_stream_slug_for('5023')).first()
        end_temp = StreamData.objects.filter(stream_slug=self.pd1.get_stream_slug_for('5023')).last()
        start_event = StreamEventData.objects.filter(stream_slug=self.pd1.get_stream_slug_for('5020')).first()
        end_event = StreamEventData.objects.filter(stream_slug=self.pd1.get_stream_slug_for('5020')).last()
        self.assertTrue(start_event.timestamp == start_temp.timestamp)
        self.assertTrue(end_event.timestamp > end_temp.timestamp)
        url = reverse('shipping-trip-detail', kwargs={'slug': self.pd1.slug})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.pd1.slug)
        self.assertEqual(deserialized['state'], 'N1')
        self.assertIsNone(deserialized['data_mask'])
        self.assertEqual(deserialized['trip_date_range']['original_start'], formatted_ts(start_temp.timestamp))
        self.assertEqual(deserialized['trip_date_range']['original_end'], formatted_ts(end_event.timestamp))
        self.assertEqual(deserialized['trip_date_range']['actual_start'], formatted_ts(start_temp.timestamp))
        actual_ts_end = end_event.timestamp + datetime.timedelta(seconds=1)
        self.assertEqual(deserialized['trip_date_range']['actual_end'], formatted_ts(actual_ts_end))
        self.assertFalse(deserialized['trip_date_range']['masked'])
        self.assertIsNone(deserialized['trip_date_range']['start_data'])
        self.assertIsNone(deserialized['trip_date_range']['end_data'])
        self.assertEqual(len(deserialized['streams']), 5)

        # Trip Archive
        resp = self.client.post(archive_url, format='json', data=archive_payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(resp.content.decode())
        block_slug = deserialized['slug']

        block = DataBlock.objects.get(slug=block_slug)
        url = reverse('shipping-trip-detail', kwargs={'slug': block_slug})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], block.slug)
        self.assertEqual(deserialized['state'], 'A')
        self.assertIsNone(deserialized['data_mask'])
        self.assertEqual(deserialized['trip_date_range']['original_start'], formatted_ts(start_temp.timestamp))
        self.assertEqual(deserialized['trip_date_range']['original_end'], formatted_ts(end_event.timestamp))
        self.assertEqual(deserialized['trip_date_range']['actual_start'], formatted_ts(start_temp.timestamp))
        self.assertEqual(deserialized['trip_date_range']['actual_end'], formatted_ts(actual_ts_end))
        self.assertFalse(deserialized['trip_date_range']['masked'])
        self.assertIsNone(deserialized['trip_date_range']['start_data'])
        self.assertIsNone(deserialized['trip_date_range']['end_data'])
        self.assertEqual(len(deserialized['streams']), 5)

        # Invalid (older) mask on start date and valid mask on end date
        mask_start = start_event.timestamp - datetime.timedelta(seconds=60)
        mask_end = end_event.timestamp - datetime.timedelta(seconds=60)
        set_data_mask(block, formatted_ts(mask_start), formatted_ts(mask_end), [], [], self.u1)
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], block.slug)
        self.assertEqual(deserialized['state'], 'A')
        self.assertIsNotNone(deserialized['data_mask'])
        self.assertEqual(deserialized['data_mask']['start'], formatted_ts(mask_start))
        self.assertEqual(deserialized['data_mask']['end'], formatted_ts(mask_end))

        self.assertEqual(deserialized['trip_date_range']['original_start'], formatted_ts(start_temp.timestamp))
        self.assertEqual(deserialized['trip_date_range']['original_end'], formatted_ts(end_event.timestamp))
        self.assertEqual(deserialized['trip_date_range']['actual_start'], formatted_ts(start_temp.timestamp))
        self.assertEqual(deserialized['trip_date_range']['actual_end'], formatted_ts(mask_end))
        self.assertTrue(deserialized['trip_date_range']['masked'])
        self.assertIsNone(deserialized['trip_date_range']['start_data'])
        self.assertIsNone(deserialized['trip_date_range']['end_data'])

        self.client.logout()
