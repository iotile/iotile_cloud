import datetime
import json

import pytz

from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from iotile_cloud.utils.gid import IOTileDeviceSlug, IOTileProjectSlug, IOTileStreamSlug, IOTileVariableSlug

from apps.devicetemplate.models import DeviceTemplate
from apps.org.models import Org, OrgMembership
from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.property.models import GenericProperty
from apps.sensorgraph.models import SensorGraph, VariableTemplate
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import display_formatted_ts
from apps.utils.utest.devices import TripDeviceMock
from apps.vartype.models import VarType

user_model = get_user_model()


class APIProjectStatusTestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()

        self.device_mock = TripDeviceMock()

        self.o2 = Org.objects.get(slug='user-org')
        self.o2.register_user(self.u2, role='a1')
        self.o3 = Org.objects.create_org(name='User Org3', created_by=self.u3)
        self.o3.register_user(self.u3)

        self.p1 = Project.objects.get(name='Project 1')
        self.pd1 = self.p1.devices.first()
        self.pd1.state = 'N1'
        self.pd1.save()

    def tearDown(self):
        self.device_mock.tearDown()
        self.userTestTearDown()

    def testGetTripStatusReport(self):
        """
        Test API to get project trip status report
        """
        url = reverse('api-project-trip-status', kwargs={'project_slug': 'p--0000-0000'})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        url = reverse('api-project-trip-status', kwargs={'project_slug': self.p1.slug})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.p1.slug)

        self.client.logout()

        # Staff has access to all
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.o2.has_access(self.u2))

        resp = self.client.get(url, format='json')
        # print(resp.content)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.p1.slug)
        self.assertEqual(deserialized['name'], self.p1.name)
        self.assertTrue('config' in deserialized)
        self.assertTrue('properties' in deserialized['config'])
        self.assertEqual(len(deserialized['config']['properties']), 2)
        self.assertEqual(deserialized['config']['properties'][0]['label'], 'Ship From')
        self.assertEqual(deserialized['config']['properties'][0]['key'], 'from')
        self.assertEqual(deserialized['config']['properties'][1]['label'], 'Ship To')
        self.assertEqual(deserialized['config']['properties'][1]['key'], 'to')
        self.assertTrue('results' in deserialized)
        self.assertEqual(len(deserialized['results']), 1)
        self.assertEqual(deserialized['results'][0]['slug'], self.pd1.slug)
        self.assertEqual(deserialized['results'][0]['state_label'], self.pd1.get_state_display())
        self.assertEqual(deserialized['results'][0]['state_id'], self.pd1.state)
        self.assertEqual(deserialized['results'][0]['last_update'], '')
        self.assertEqual(deserialized['results'][0]['properties']['from'], 'Here')
        self.assertEqual(deserialized['results'][0]['properties']['to'], 'There')

        # Now ad trip update event and try again
        project_slug = IOTileProjectSlug(self.p1.slug)
        variable_slug = IOTileVariableSlug(SYSTEM_VID['TRIP_UPDATE'], project=project_slug)
        stream_slug = IOTileStreamSlug()
        stream_slug.from_parts(project=project_slug, device=self.pd1.slug, variable=variable_slug)
        event = StreamEventData.objects.create(
            stream_slug=str(stream_slug),
            timestamp=timezone.now(),
            extra_data={
                "Below 17C": 0,
                "Max Peak (G)": 40.621,
                "Min Temp (C)": 22.56,
                "Max Humidity (% RH)": 39.634765625,
                "DeltaV at Max Peak (in/s)": 52.67529065551758
            }
        )
        self.assertEqual(StreamEventData.objects.filter(stream_slug=str(stream_slug)).count(), 1)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.p1.slug)
        self.assertEqual(deserialized['results'][0]['slug'], self.pd1.slug)
        self.assertEqual(deserialized['results'][0]['state_label'], self.pd1.get_state_display() + ' (Update)')
        self.assertEqual(deserialized['results'][0]['state_id'], self.pd1.state)
        self.assertEqual(deserialized['results'][0]['last_update'], display_formatted_ts(event.timestamp))

        variable_slug = IOTileVariableSlug(SYSTEM_VID['TRIP_SUMMARY'], project=project_slug)
        stream_slug = IOTileStreamSlug()
        stream_slug.from_parts(project=project_slug, device=self.pd1.slug, variable=variable_slug)
        event = StreamEventData.objects.create(
            stream_slug=str(stream_slug),
            timestamp=timezone.now(),
            extra_data={
                "Below 17C": 0,
                "Max Peak (G)": 40.621,
                "Min Temp (C)": 22.56,
                "Max Humidity (% RH)": 39.634765625,
                "DeltaV at Max Peak (in/s)": 52.67529065551758
            }
        )
        self.assertEqual(StreamEventData.objects.filter(stream_slug=str(stream_slug)).count(), 1)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.p1.slug)
        self.assertEqual(deserialized['results'][0]['slug'], self.pd1.slug)
        self.assertEqual(deserialized['results'][0]['state_label'], 'Normal - Trip Ended')
        self.assertEqual(deserialized['results'][0]['last_update'], display_formatted_ts(event.timestamp))

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertFalse(self.o2.has_access(self.u3))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Test that it works for members
        self.o2.register_user(self.u3, role='m1')
        self.assertTrue(self.o2.is_member(self.u3))
        self.assertTrue(self.o2.has_permission(self.u1, 'can_read_device_properties'))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], self.p1.slug)
        self.assertEqual(deserialized['results'][0]['slug'], self.pd1.slug)
        self.assertEqual(deserialized['results'][0]['state_label'], 'Normal - Trip Ended')
        self.assertEqual(deserialized['results'][0]['last_update'], display_formatted_ts(event.timestamp))

        self.client.logout()
