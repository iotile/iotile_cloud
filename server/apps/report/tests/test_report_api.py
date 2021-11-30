from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.datablock.models import DataBlock
from apps.datablock.worker.archive_device_data import ArchiveDeviceDataAction
from apps.streamevent.models import StreamEventData
from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.test_util import TestMixin
from apps.utils.utest.devices import TripDeviceMock

from ..models import *
from ..worker.report_generator import *

user_model = get_user_model()


class ReportGeneratorAPITestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()

        self.device_mock = TripDeviceMock()

        self.o2 = Org.objects.get(slug='user-org')
        self.o2.register_user(self.u2)
        self.p1 = Project.objects.get(name='Project 1')
        self.pd1 = self.p1.devices.first()

    def tearDown(self):
        DataBlock.objects.all().delete()
        self.device_mock.tearDown()

        self.userTestTearDown()

    def testReportGenerate(self):
        url = reverse('api-report-summary')
        payload = {
            'device_slug': 'd--1234', # Not in Org
            'generator': 'default' # Not allowed
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        payload['notification_recipients'] = 'foo'
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        payload['notification_recipients'] = ['email:user3@test.com']
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        payload['generator'] = 'end_of_trip'
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        payload['device_slug'] = self.pd1.slug
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        stream_slug = self.pd1.get_stream_slug_for(SYSTEM_VID['TRIP_SUMMARY'])
        self.assertEqual(StreamEventData.objects.filter(stream_slug=str(stream_slug)).count(), 1)
        summary = StreamEventData.objects.filter(stream_slug=str(stream_slug)).first()

        trip_data = summary.extra_data
        self.assertEqual(trip_data['Device'], self.pd1.slug)
        self.assertEqual(trip_data['Event Count'], 10)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testReportGenerateOnDataBlock(self):

        # Archive
        block = DataBlock.objects.create(org=self.pd1.org, title='test', device=self.pd1, block=1, created_by=self.u1)
        action = ArchiveDeviceDataAction()
        action._block = block
        action._device = self.pd1
        action.execute(arguments={'data_block_slug': block.slug})

        url = reverse('api-report-summary')
        payload = {
            'device_slug': self.pd1.slug,
            'generator': 'end_of_trip',
            'notification_recipients': []
        }

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        payload['device_slug'] = block.slug
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['detail'], 'Illegal device slug: {}'.format(block.slug))

        payload['slug'] = block.slug
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['detail'], 'slug and device_slug cannot be used together. Use slug')

        del payload['device_slug']
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        stream_slug = block.get_stream_slug_for(SYSTEM_VID['TRIP_SUMMARY'])
        self.assertEqual(StreamEventData.objects.filter(stream_slug=str(stream_slug)).count(), 1)
        summary = StreamEventData.objects.filter(stream_slug=str(stream_slug)).first()

        trip_data = summary.extra_data
        self.assertEqual(trip_data['Device'], block.slug)
        self.assertEqual(trip_data['Event Count'], 10)

        self.client.logout()

    def testReportGenerateOnDataBlockWithNoSummaryStream(self):

        # Archive
        block = DataBlock.objects.create(org=self.pd1.org, title='test', device=self.pd1, block=1, created_by=self.u1)
        action = ArchiveDeviceDataAction()
        action._block = block
        action._device = self.pd1
        action.execute(arguments={'data_block_slug': block.slug})

        stream_slug = block.get_stream_slug_for(SYSTEM_VID['TRIP_SUMMARY'])
        summary_stream = StreamId.objects.get(slug=stream_slug)
        summary_stream.delete()

        url = reverse('api-report-summary')
        payload = {
            'slug': block.slug,
            'generator': 'end_of_trip',
            'notification_recipients': []
        }

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        stream_slug = block.get_stream_slug_for(SYSTEM_VID['TRIP_SUMMARY'])
        self.assertEqual(StreamEventData.objects.filter(stream_slug=str(stream_slug)).count(), 1)

        self.client.logout()

