import json
import datetime
import pytz
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from iotile_cloud.utils.gid import IOTileStreamSlug, IOTileVariableSlug, IOTileProjectSlug, IOTileDeviceSlug

from apps.utils.test_util import TestMixin
from apps.utils.utest.devices import TripDeviceMock
from apps.utils.iotile.variable import SYSTEM_VID
from apps.org.models import OrgMembership, Org
from apps.physicaldevice.models import Device
from apps.devicetemplate.models import DeviceTemplate
from apps.vartype.models import VarType
from apps.sensorgraph.models import SensorGraph, VariableTemplate
from apps.stream.models import StreamVariable, StreamId
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.property.models import GenericProperty
from apps.project.models import Project
from apps.configattribute.models import ConfigAttribute
from apps.datablock.models import DataBlock
from apps.utils.timezone_utils import display_formatted_ts
from apps.datablock.worker.archive_device_data import ArchiveDeviceDataAction


user_model = get_user_model()


class APIOrgQualityTestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()

        self.device_mock = TripDeviceMock()

        self.o2 = Org.objects.get(slug='user-org')
        self.o2.register_user(self.u2, role='a1')
        self.o3 = Org.objects.create_org(name='User Org3', created_by=self.u3)
        self.o3.register_user(self.u3)

        self.p1 = Project.objects.get(name='Project 1')
        self.pd1 = self.p1.devices.first()

        config = {
            "summary_keys": [
                "START (UTC)",
                "END (UTC)"
            ],
            "property_keys": [
                "Customer",
                "Ship From",
                "Ship To"
            ]
        }
        ConfigAttribute.objects.get_or_create_attribute(
            target=self.o2,
            name=':report:trip_quality:config',
            data=config,
            updated_by=self.u1
        )

    def tearDown(self):
        ConfigAttribute.objects.all().delete()
        self.device_mock.tearDown()
        self.userTestTearDown()

    def testGetTripStatusReport(self):
        """
        Test API to get project trip status report
        """
        url = reverse('api-org-quality-summary', kwargs={'org_slug': 'foo'})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        url = reverse('api-org-quality-summary', kwargs={'org_slug': self.o2.slug})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.o2.slug)

        self.client.logout()

        # Staff has access to all
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.o2.has_access(self.u2))

        resp = self.client.get(url, format='json')
        # print(resp.content)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.o2.slug)
        self.assertEqual(deserialized['name'], self.o2.name)
        self.assertTrue('config' in deserialized)
        self.assertTrue('property_keys' in deserialized['config'])
        self.assertEqual(len(deserialized['config']['property_keys']), 3)
        self.assertTrue('results' in deserialized)
        self.assertEqual(len(deserialized['results']), 0)

        # Create Summary Event
        project_slug = IOTileProjectSlug(self.p1.slug)
        variable_slug = IOTileVariableSlug(SYSTEM_VID['TRIP_SUMMARY'], project=project_slug)
        stream_slug = IOTileStreamSlug()
        stream_slug.from_parts(project=project_slug, device=self.pd1.slug, variable=variable_slug)
        event = StreamEventData.objects.create(
            stream_slug=str(stream_slug),
            timestamp=timezone.now(),
            extra_data={
                "Device": "d--0000-0000-0000-0512",
                "Above 30C": 0,
                "Below 17C": 639,
                "END (UTC)": "Not Available",
                "Event Count": 92,
                "START (UTC)": "Not Available",
                "Max Peak (G)": 42.042,
                "Max Temp (C)": 25.5,
                "Min Temp (C)": 14.060000000000002,
                "Duration (Days)": 25.615692141203702,
                "Median Temp (C)": 18.420000000000016,
                "MaxDeltaV (in/s)": 66.47352005004882,
                "Last event at (UTC)": "2018-01-10 08:44:48",
                "Max Humidity (% RH)": 45.1103515625,
                "Max Pressure (Mbar)": 1037.38,
                "Min Humidity (% RH)": 17.3544921875,
                "Min Pressure (Mbar)": 819.95,
                "First event at (UTC)": "2017-12-15 17:58:13",
                "Peak at MaxDeltaV (G)": 2.156,
                "Median Humidity (% RH)": 19.041015625,
                "Median Pressure (Mbar)": 1016.15,
                "TimeStamp(MaxPeak) (UTC)": "2017-12-15 17:58:13",
                "DeltaV at Max Peak (in/s)": 26.585683441162107,
                "TimeStamp(MaxDeltaV) (UTC)": "2017-12-21 04:40:02"
            }
        )
        self.assertEqual(StreamEventData.objects.filter(stream_slug=str(stream_slug)).count(), 1)

        # Archive device
        block = DataBlock.objects.create(org=self.o2, title='Archive 1', device=self.pd1, block=1, created_by=self.u1)
        action = ArchiveDeviceDataAction()
        action._block = block
        action._device = self.pd1
        action.execute(arguments={'data_block_slug': block.slug})

        resp = self.client.get(url, format='json')
        # print(resp.content)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.o2.slug)
        self.assertEqual(deserialized['name'], self.o2.name)
        self.assertTrue('config' in deserialized)
        self.assertTrue('summary_keys' in deserialized['config'])
        self.assertEqual(len(deserialized['config']['summary_keys']), 2)
        self.assertTrue('property_keys' in deserialized['config'])
        self.assertEqual(len(deserialized['config']['property_keys']), 3)
        self.assertEqual(deserialized['count'], 1)
        self.assertTrue('results' in deserialized)
        self.assertEqual(len(deserialized['results']), 1)
        self.assertEqual(deserialized['results'][0]['slug'], block.slug)
        self.assertEqual(deserialized['results'][0]['label'], block.title)
        self.assertEqual(deserialized['results'][0]['summary_date'], display_formatted_ts(event.timestamp))
        # print(deserialized['results'][0])
        self.assertTrue('data' in deserialized['results'][0])
        self.assertTrue('properties' in deserialized['results'][0]['data'])
        self.assertEqual(deserialized['results'][0]['data']['properties']['Ship From'], 'Here')
        self.assertEqual(deserialized['results'][0]['data']['properties']['Ship To'], 'There')

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertFalse(self.o2.has_access(self.u3))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

