import datetime
import json

import dateutil.parser

from django.utils import timezone

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.org.models import Org
from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.utils.test_util import TestMixin

from ..models import *


class StreamAliasTapAPITestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.p1.project_template = self.pt1
        self.p1.save()
        self.p2.project_template = self.pt1
        self.p2.save()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=1,
        )
        self.v2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p2, created_by=self.u3, lid=2,
        )
        self.pd11 = Device.objects.create_device(project=self.p1, label='d11', template=self.dt1, created_by=self.u2)
        self.pd12 = Device.objects.create_device(project=self.p1, label='d12', template=self.dt1, created_by=self.u2)
        self.pd21 = Device.objects.create_device(project=self.p2, label='d21', template=self.dt1, created_by=self.u3)
        self.pd22 = Device.objects.create_device(project=self.p2, label='d22', template=self.dt1, created_by=self.u3)
        
        self.sa1 = StreamAlias.objects.create(
            name='some alias',
            org=self.o2,
            created_by=self.u2,
        )
        self.s11 = StreamId.objects.create_stream(
            project=self.p1,
            variable=self.v1,
            device=self.pd11,
            created_by=self.u2
        )
        self.s12 = StreamId.objects.create_stream(
            project=self.p1,
            variable=self.v1,
            device=self.pd12,
            created_by=self.u2
        )
        
        self.sa2 = StreamAlias.objects.create(
            name='some other alias',
            org=self.o3,
            created_by=self.u1,
        )
        self.s21 = StreamId.objects.create_stream(
            project=self.p2,
            variable=self.v2,
            device=self.pd21,
            created_by=self.u3
        )
        self.s22 = StreamId.objects.create_stream(
            project=self.p2,
            variable=self.v2,
            device=self.pd22,
            created_by=self.u3
        )

        self.dt = dateutil.parser.parse('2016-09-28T10:00:00Z')

        self.sat11 = StreamAliasTap.objects.create(
            alias=self.sa1,
            timestamp=self.dt + datetime.timedelta(seconds=20),
            stream=self.s11,
            created_by=self.u2
        )
        self.sat12 = StreamAliasTap.objects.create(
            alias=self.sa1,
            timestamp=self.dt + datetime.timedelta(seconds=60),
            stream=self.s12,
            created_by=self.u2
        )
        self.sat13 = StreamAliasTap.objects.create(
            alias=self.sa1,
            timestamp=self.dt + datetime.timedelta(seconds=80),
            stream=self.s11,
            created_by=self.u2
        )
        self.sat21 = StreamAliasTap.objects.create(
            alias=self.sa2,
            timestamp=self.dt,
            stream=self.s21,
            created_by=self.u3
        )
        self.sat22 = StreamAliasTap.objects.create(
            alias=self.sa2,
            timestamp=self.dt + datetime.timedelta(seconds=50),
            stream=self.s22,
            created_by=self.u3
        )

        for i, n in enumerate(('11', '12', '21', '22')):
            for p in range(0, 11):
                StreamData.objects.create(
                    stream_slug=getattr(self, 's{}'.format(n)).slug,
                    type='Num',
                    timestamp=self.dt + p * datetime.timedelta(seconds=10),
                    int_value= 100 * i + p
                )

        StreamEventData.objects.create(
            timestamp=self.dt,
            device_timestamp=100,
            stream_slug=self.s11.slug,
            streamer_local_id=1
        )
        StreamEventData.objects.create(
            timestamp=self.dt + datetime.timedelta(seconds=70),
            device_timestamp=170,
            stream_slug=self.s12.slug,
            streamer_local_id=2
        )
        StreamEventData.objects.create(
            timestamp=self.dt + datetime.timedelta(seconds=90),
            device_timestamp=190,
            stream_slug=self.s11.slug,
            streamer_local_id=3
        )
        StreamEventData.objects.create(
            timestamp=self.dt + datetime.timedelta(seconds=60),
            device_timestamp=160,
            stream_slug=self.s22.slug,
            streamer_local_id=4
        )

    def tearDown(self):
        StreamAliasTap.objects.all().delete()
        StreamAlias.objects.all().delete()
        StreamId.objects.all().delete()
        self.projectTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testGetStreamAliasTap(self):
        """
        Ensure we can call GET on the Stream Alias Tap API.
        """
        url = reverse('streamaliastap-list')

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        # Staff has access to all if staff argument is provided
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        resp = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 5)

        detail_url1 = reverse('streamaliastap-detail', kwargs={'pk': self.sat11.id})
        detail_url2 = reverse('streamaliastap-detail', kwargs={'pk': self.sat21.id})

        resp = self.client.get(detail_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.get(detail_url2, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.get(detail_url1+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], self.sat11.id)
        self.assertEqual(deserialized['alias'], self.sa1.slug)
        self.assertEqual(deserialized['timestamp'], '2016-09-28T10:00:20Z')
        self.assertEqual(deserialized['stream'], self.s11.slug)

        self.client.logout()

        # Normal users have access to their Stream Aliases only
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 3)  

        resp = self.client.get(detail_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], self.sat11.id)

        resp = self.client.get(detail_url2, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        resp = self.client.get(detail_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.get(detail_url2, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], self.sat21.id)
        
        self.client.logout()

    def testPostStreamAliasTap(self):
        """
        Ensure we can call POST on the Stream Alias Tap API.
        """
        url = reverse('streamaliastap-list')
        self.assertEqual(StreamAliasTap.objects.all().count(), 5)

        # added by staff
        payload = {
            'alias': self.sa2.slug,
            'timestamp': self.dt + datetime.timedelta(seconds=70),
            'stream': self.s21.slug,
        }
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamAliasTap.objects.all().count(), 6)
        tap = StreamAliasTap.objects.all().last()
        self.assertEqual(tap.alias, self.sa2)
        self.assertEqual(tap.timestamp, self.dt + datetime.timedelta(seconds=70))
        self.assertEqual(tap.stream, self.s21)
        self.assertEqual(tap.created_by, self.u1)    

        # inconsistent alias and stream
        payload = {
            'alias': self.sa1.slug,
            'timestamp': self.dt + datetime.timedelta(seconds=70),
            'stream': self.s21.slug,
        }
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(StreamAliasTap.objects.all().count(), 6)        

        self.client.logout()

        # added by member
        payload = {
            'alias': self.sa2.slug,
            'timestamp': self.dt + datetime.timedelta(seconds=85),
            'stream': self.s22.slug,
        }
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamAliasTap.objects.all().count(), 7)        
        tap = StreamAliasTap.objects.all().last()
        self.assertEqual(tap.alias, self.sa2)
        self.assertEqual(tap.timestamp, self.dt + datetime.timedelta(seconds=85))
        self.assertEqual(tap.stream, self.s22)
        self.assertEqual(tap.created_by, self.u3)    

        self.client.logout()

        # non-member
        payload = {
            'alias': self.sa2.slug,
            'timestamp': self.dt + datetime.timedelta(seconds=85),
            'stream': self.s22.slug,
        }
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(StreamAliasTap.objects.all().count(), 7)        

        membership = self.o3.register_user(self.u2, role='m1')
        membership.permissions['can_manage_stream_aliases'] = False
        membership.save()

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(StreamAliasTap.objects.all().count(), 7)        

        self.client.logout()

    def testPatchStreamAliasTap(self):
        """
        Ensure we can call PATCH on the Stream Alias Tap API.
        """
        url = reverse('streamaliastap-detail', kwargs={'pk': self.sat11.id})

        # changed by staff
        payload = {
            'timestamp': self.dt,
        }
        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.patch(url+'?staff=1', data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        tap = StreamAliasTap.objects.get(pk=self.sat11.id)
        self.assertEqual(tap.timestamp, payload['timestamp'])

        self.client.logout()

        # changed by member
        payload = {
            'stream': self.s12,
        }
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        tap = StreamAliasTap.objects.get(pk=self.sat11.id)
        self.assertEqual(tap.stream, payload['stream'])

        # alias and stream from forbidden org
        payload = {
            'alias': self.sa2.slug,
            'stream': self.s21.slug,
        }
        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        # changed by non-member
        payload = {
            'timestamp': self.dt + datetime.timedelta(seconds=40),
        }
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        membership = self.o2.register_user(self.u3, role='m1')
        membership.permissions['can_manage_stream_aliases'] = False
        membership.save()

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        membership.permissions['can_manage_stream_aliases'] = True
        membership.save()

        # with stream from other org
        payload = {
            'stream': self.s21,
        }
        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # with stream from same org
        payload = {
            'stream': self.s11,
        }
        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testPutStreamAliasTap(self):
        """
        Ensure we can call PUT on the Stream Alias Tap API.
        """
        url = reverse('streamaliastap-detail', kwargs={'pk': self.sat11.id})

        # changed by staff
        payload = {
            'alias': self.sat11.alias.slug,
            'stream': self.sat11.stream.slug,
            'timestamp': self.dt,
        }
        resp = self.client.put(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.put(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.put(url+'?staff=1', data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        tap = StreamAliasTap.objects.get(pk=self.sat11.id)
        self.assertEqual(tap.timestamp, payload['timestamp'])

        self.client.logout()

        # changed by member
        payload = {
            'alias': self.sat11.alias.slug,
            'stream': self.s12.slug,
            'timestamp': self.sat11.timestamp,
        }
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.put(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        tap = StreamAliasTap.objects.get(pk=self.sat11.id)
        self.assertEqual(tap.stream.slug, payload['stream'])

        # alias and stream from forbidden org
        payload = {
            'alias': self.sa2.slug,
            'stream': self.s21.slug,
            'timestamp': self.dt + datetime.timedelta(seconds=40),
        }
        resp = self.client.put(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        # changed by non-member
        payload = {
            'alias': self.sat11.alias.slug,
            'stream': self.sat11.stream.slug,
            'timestamp': self.dt + datetime.timedelta(seconds=40),
        }
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.put(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        membership = self.o2.register_user(self.u3, role='m1')
        membership.permissions['can_manage_stream_aliases'] = False
        membership.save()

        resp = self.client.put(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        membership.permissions['can_manage_stream_aliases'] = True
        membership.save()

        # with stream from other org
        payload = {
            'alias': self.sat11.alias.slug,
            'stream': self.s21.slug,
            'timestamp': self.sat11.timestamp,        
        }
        resp = self.client.put(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # with stream from same org
        payload = {
            'alias': self.sat11.alias.slug,
            'stream': self.s11.slug,
            'timestamp': self.sat11.timestamp,
        }
        resp = self.client.put(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testDeleteStreamAliasTap(self):
        """
        Ensure we can call DELETE on the Stream Alias Tap API.
        """
        url = reverse('streamaliastap-detail', kwargs={'pk': self.sat12.id})

        self.assertEqual(StreamAlias.objects.all().count(), 2)
        self.assertEqual(StreamAliasTap.objects.all().count(), 5)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAliasTap.objects.filter(pk=self.sat12.id).count(), 1)

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(StreamAlias.objects.all().count(), 2)
        self.assertEqual(StreamAliasTap.objects.all().count(), 5)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAliasTap.objects.filter(pk=self.sat12.id).count(), 1)

        # Staff can delete if staff argument is provided
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(StreamAlias.objects.all().count(), 2)
        self.assertEqual(StreamAliasTap.objects.all().count(), 5)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAliasTap.objects.filter(pk=self.sat12.id).count(), 1)

        resp = self.client.delete(url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(StreamAlias.objects.all().count(), 2)
        self.assertEqual(StreamAliasTap.objects.all().count(), 4)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAliasTap.objects.filter(pk=self.sat12.id).count(), 0)

        self.client.logout()

        self.sat12 = StreamAliasTap.objects.create(
            alias=self.sa1,
            timestamp=self.dt + datetime.timedelta(seconds=60),
            stream=self.s12,
            created_by=self.u2
        )
        url = reverse('streamaliastap-detail', kwargs={'pk': self.sat12.id})

        # Member can delete
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        self.assertEqual(StreamAlias.objects.all().count(), 2)
        self.assertEqual(StreamAliasTap.objects.all().count(), 5)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAliasTap.objects.filter(pk=self.sat12.id).count(), 1)

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(StreamAlias.objects.all().count(), 2)
        self.assertEqual(StreamAliasTap.objects.all().count(), 4)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAliasTap.objects.filter(pk=self.sat12.id).count(), 0)

        self.client.logout()

        self.sat12 = StreamAliasTap.objects.create(
            alias=self.sa1,
            timestamp=self.dt + datetime.timedelta(seconds=60),
            stream=self.s12,
            created_by=self.u2
        )
        url = reverse('streamaliastap-detail', kwargs={'pk': self.sat12.id})

        # Non-Member can't delete
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        self.assertEqual(StreamAlias.objects.all().count(), 2)
        self.assertEqual(StreamAliasTap.objects.all().count(), 5)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAliasTap.objects.filter(pk=self.sat12.id).count(), 1)

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(StreamAlias.objects.all().count(), 2)
        self.assertEqual(StreamAliasTap.objects.all().count(), 5)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAliasTap.objects.filter(pk=self.sat12.id).count(), 1)

        # Permissions are required to delete stream alias
        membership = self.o2.register_user(self.u3, role='m1')
        membership.permissions['can_manage_stream_aliases'] = False
        membership.save()

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(StreamAlias.objects.all().count(), 2)
        self.assertEqual(StreamAliasTap.objects.all().count(), 5)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAliasTap.objects.filter(pk=self.sat12.id).count(), 1)

        self.client.logout()

    def testFilter(self):
        url = reverse('streamaliastap-list')

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        sa3 = StreamAlias.objects.create(
            name='new alias',
            org=self.o2,
            created_by=self.u2,
        )
        sat31 = StreamAliasTap.objects.create(
            alias=sa3,
            timestamp=self.dt,
            stream=self.s11,
            created_by=self.u2
        )

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)

        resp = self.client.get(url+'?target={}'.format(self.sa1.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 3)

        resp = self.client.get(url+'?target={}'.format(sa3.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['alias'], sa3.slug)
        self.assertEqual(deserialized['results'][0]['timestamp'], '2016-09-28T10:00:00Z')
        self.assertEqual(deserialized['results'][0]['stream'], self.s11.slug)

        self.client.logout()
