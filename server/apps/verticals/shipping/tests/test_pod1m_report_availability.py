import json
from django.contrib.auth import get_user_model

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin
from apps.utils.utest.devices import TripDeviceMock
from apps.project.models import Project
from apps.org.models import Org
from apps.streamevent.models import StreamEventData
from apps.streamdata.models import StreamData
from apps.physicaldevice.models import Device
from apps.datablock.models import DataBlock
from apps.utils.data_mask.mask_utils import set_data_mask
from apps.report.models import GeneratedUserReport
from apps.datablock.worker.archive_device_data import ArchiveDeviceDataAction

user_model = get_user_model()


class ReportAvailabilityPod1MTestCase(TestMixin, APITestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()

        self.device_mock = TripDeviceMock()

        self.o2 = Org.objects.get(slug='user-org')
        self.p1 = Project.objects.get(name='Project 1')
        self.pd1 = self.p1.devices.first()

    def tearDown(self):
        GeneratedUserReport.objects.all().delete()
        self.orgTestTearDown()
        self.userTestTearDown()
        self.device_mock.tearDown()

    def testMock(self):
        self.device_mock.testMock(self)

    def testShippingDeviceReportAvailability(self):
        sg = self.pd1.sg
        self.assertTrue('Shipping' in sg.name)
        self.assertTrue('POD-1M' in self.pd1.template.family)
        pd2 = Device.objects.create(id=1, label="d1", template=self.pd1.template, sg=sg, created_by=self.u1)
        self.assertTrue('shipping' in pd2.sg.slug.split('-'))
        payload = {
            'slug': self.pd1.slug
        }

        url = reverse('generateduserreport-availability')
        self.assertEqual(GeneratedUserReport.objects.count(), 0)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['slug'], self.pd1.slug)
        self.assertEqual(deserialized['code'], 'AVAILABLE')
        self.assertEqual(len(deserialized['extra']['reports']), 2)

        # Test with Data Mask. Mask out all data
        set_data_mask(self.pd1, None, '2016-01-10T10:00:00Z', [], [], self.u1)
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['slug'], self.pd1.slug)
        self.assertEqual(deserialized['code'], 'NOT_AVAILABLE')
        self.assertEqual(deserialized['extra'], {})

        # Test without Events
        StreamEventData.objects.all().delete()
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['slug'], self.pd1.slug)
        self.assertEqual(deserialized['code'], 'AVAILABLE')
        self.assertEqual(len(deserialized['extra']['reports']), 2)

        # Test without Events
        StreamData.objects.all().delete()
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['slug'], self.pd1.slug)
        self.assertEqual(deserialized['code'], 'NOT_AVAILABLE')
        self.assertEqual(deserialized['extra'], {})

        self.client.logout()

    def testShippingDataBlockReportAvailability(self):
        sg = self.pd1.sg
        self.assertTrue('Shipping' in sg.name)
        self.assertTrue('POD-1M' in self.pd1.template.family)
        pd2 = Device.objects.create(id=1, label="d1", template=self.pd1.template, sg=sg, created_by=self.u1)
        self.assertTrue('shipping' in pd2.sg.slug.split('-'))

        # Archive first
        block = DataBlock.objects.create(org=self.pd1.org, title='test', device=self.pd1, block=1, created_by=self.u1)
        action = ArchiveDeviceDataAction()
        action._block = block
        action._device = self.pd1
        action.execute(arguments={'data_block_slug': block.slug})

        payload = {
            'slug': block.slug
        }

        url = reverse('generateduserreport-availability')
        self.assertEqual(GeneratedUserReport.objects.count(), 0)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['slug'], block.slug)
        self.assertEqual(deserialized['code'], 'AVAILABLE')
        self.assertEqual(len(deserialized['extra']['reports']), 2)

        # Test with Data Mask. Mask out all data
        set_data_mask(block, None, '2016-01-10T10:00:00Z', [], [], self.u1)
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['slug'], block.slug)
        self.assertEqual(deserialized['code'], 'NOT_AVAILABLE')
        self.assertEqual(deserialized['extra'], {})

        # Test without Events
        StreamEventData.objects.all().delete()
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['slug'], block.slug)
        self.assertEqual(deserialized['code'], 'AVAILABLE')
        self.assertEqual(len(deserialized['extra']['reports']), 2)

        self.client.logout()


