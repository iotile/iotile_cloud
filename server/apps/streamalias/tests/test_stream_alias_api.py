import datetime
import json

import dateutil.parser

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


class StreamAliasAPITestCase(TestMixin, APITestCase):

    def _create_sa0(self):
        self.sa0 = StreamAlias.objects.create(
            name='some alias',
            org=self.o2,
            created_by=self.u1,
        )
        self.sat01 = StreamAliasTap.objects.create(
            alias=self.sa0,
            timestamp=self.dt + datetime.timedelta(seconds=20),
            stream=self.s01,
            created_by=self.u2
        )
        self.sat02 = StreamAliasTap.objects.create(
            alias=self.sa0,
            timestamp=self.dt + datetime.timedelta(seconds=60),
            stream=self.s02,
            created_by=self.u2
        )
        self.sat03 = StreamAliasTap.objects.create(
            alias=self.sa0,
            timestamp=self.dt + datetime.timedelta(seconds=80),
            stream=self.s01,
            created_by=self.u2
        )

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
            name='some other alias',
            org=self.o2,
            created_by=self.u2,
        )
        self.sa2 = StreamAlias.objects.create(
            name='yet another alias',
            org=self.o3,
            created_by=self.u1,
        )

        self.s01 = StreamId.objects.create_stream(
            project=self.p1,
            variable=self.v1,
            device=self.pd11,
            created_by=self.u2
        )
        self.s02 = StreamId.objects.create_stream(
            project=self.p1,
            variable=self.v1,
            device=self.pd12,
            created_by=self.u2
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

        self._create_sa0()

        for i, n in enumerate(('01', '02', '21', '22')):
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
            stream_slug=self.s01.slug,
            streamer_local_id=1
        )
        StreamEventData.objects.create(
            timestamp=self.dt + datetime.timedelta(seconds=70),
            device_timestamp=170,
            stream_slug=self.s02.slug,
            streamer_local_id=2
        )
        StreamEventData.objects.create(
            timestamp=self.dt + datetime.timedelta(seconds=90),
            device_timestamp=190,
            stream_slug=self.s01.slug,
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

    def testGetStreamAlias(self):
        """
        Ensure we can call GET on the Stream Alias API.
        """
        url = reverse('streamalias-list')

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        # Staff has access to all if staff argument is provided
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        sa1 = StreamAlias.objects.create(name='Stream Alias 10', created_by=self.u2, org=self.o2)
        sa2 = StreamAlias.objects.create(name='Stream Alias 20', created_by=self.u3, org=self.o3)
        detail_url1 = reverse('streamalias-detail', kwargs={'slug': sa1.slug})
        detail_url2 = reverse('streamalias-detail', kwargs={'slug': sa2.slug})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        resp = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 5)

        resp = self.client.get(detail_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.get(detail_url2, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.get(detail_url1+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], sa1.id)
        self.assertEqual(deserialized['name'], sa1.name)
        self.assertEqual(deserialized['slug'], sa1.slug)
        self.assertEqual(deserialized['org'], self.o2.slug)

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
        self.assertEqual(deserialized['id'], sa1.id)

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
        self.assertEqual(deserialized['id'], sa2.id)
        
        self.client.logout()

    def testPostStreamAlias(self):
        """
        Ensure we can call POST on the Stream Alias API.
        """
        url = reverse('streamalias-list')
        self.assertEqual(StreamAlias.objects.all().count(), 3)

        payload = {
            'name': 'Added by Staff',
            'org': self.o2.slug,
        }
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamAlias.objects.all().count(), 4)
        alias = StreamAlias.objects.all().last()
        self.assertEqual(alias.name, 'Added by Staff')
        self.assertEqual(alias.org, self.o2)    
        self.assertEqual(alias.created_by, self.u1)    

        self.client.logout()

        payload = {
            'name': 'Added by Member',
            'org': self.o2.slug,
        }
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamAlias.objects.all().count(), 5)        
        alias = StreamAlias.objects.all().last()
        self.assertEqual(alias.name, 'Added by Member')
        self.assertEqual(alias.org, self.o2)
        self.assertEqual(alias.created_by, self.u2)    

        self.client.logout()

        payload = {
            'name': 'ERROR Non-member',
            'org': self.o2.slug
        }
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(StreamAlias.objects.all().count(), 5)        

        membership = self.o2.register_user(self.u3, role='m1')
        membership.permissions['can_manage_stream_aliases'] = False
        membership.save()

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(StreamAlias.objects.all().count(), 5)        

        self.client.logout()

    def testPatchStreamAlias(self):
        """
        Ensure we can call PATCH on the Stream Alias API.
        """
        url = reverse('streamalias-detail', kwargs={'slug': self.sa0.slug})

        payload = {
            'name': 'Changed by Staff',
        }
        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.patch(url+'?staff=1', data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        sa0 = StreamAlias.objects.get(pk=self.sa0.id)
        self.assertEqual(sa0.name, payload['name'])

        self.client.logout()

        payload = {
            'name': 'Changed by Member',
        }
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        sa0 = StreamAlias.objects.get(pk=self.sa0.id)
        self.assertEqual(sa0.name, payload['name'])

        # forbidden org
        payload = {
            'org': self.o3.slug,
        }
        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        payload = {
            'name': 'Non-member',
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

        self.client.logout()

    def testPutStreamAlias(self):
        """
        Ensure we can call PUT on the Stream Alias API.
        """
        url = reverse('streamalias-detail', kwargs={'slug': self.sa0.slug})

        payload = {
            'name': 'Changed by Staff',
            'org': self.sa0.org.slug,
        }
        resp = self.client.put(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.put(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.put(url+'?staff=1', data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        sa0 = StreamAlias.objects.get(pk=self.sa0.id)
        self.assertEqual(sa0.name, payload['name'])

        self.client.logout()

        payload = {
            'name': 'Changed by Member',
            'org': self.sa0.org.slug,
        }
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.put(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        sa0 = StreamAlias.objects.get(pk=self.sa0.id)
        self.assertEqual(sa0.name, payload['name'])

        payload = {
            'name': 'Forbidden org',
            'org': self.o3.slug,
        }
        resp = self.client.put(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        payload = {
            'name': 'Non-member',
            'org': self.sa0.org.slug,
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

        self.client.logout()

    def testDeleteStreamAlias(self):
        """
        Ensure we can call DELETE on the Stream Alias API.
        """
        url = reverse('streamalias-detail', kwargs={'slug': self.sa0.slug})

        self.assertEqual(StreamAlias.objects.all().count(), 3)
        self.assertEqual(StreamAliasTap.objects.all().count(), 5)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAlias.objects.filter(pk=self.sa0.id).count(), 1)

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(StreamAlias.objects.all().count(), 3)
        self.assertEqual(StreamAliasTap.objects.all().count(), 5)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAlias.objects.filter(pk=self.sa0.id).count(), 1)

        # Staff can delete if staff argument is provided
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(StreamAlias.objects.all().count(), 3)
        self.assertEqual(StreamAliasTap.objects.all().count(), 5)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAlias.objects.filter(pk=self.sa0.id).count(), 1)

        resp = self.client.delete(url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        # Delete alias and all taps associated to it (but not the data)
        self.assertEqual(StreamAlias.objects.all().count(), 2)
        self.assertEqual(StreamAliasTap.objects.all().count(), 2)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAlias.objects.filter(pk=self.sa0.id).count(), 0)

        self.client.logout()

        self._create_sa0()
        url = reverse('streamalias-detail', kwargs={'slug': self.sa0.slug})

        # Member can delete
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        self.assertEqual(StreamAlias.objects.all().count(), 3)
        self.assertEqual(StreamAliasTap.objects.all().count(), 5)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAlias.objects.filter(pk=self.sa0.id).count(), 1)

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        # Delete alias and all taps associated to it (but not the data)
        self.assertEqual(StreamAlias.objects.all().count(), 2)
        self.assertEqual(StreamAliasTap.objects.all().count(), 2)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAlias.objects.filter(pk=self.sa0.id).count(), 0)

        self.client.logout()

        self._create_sa0()
        url = reverse('streamalias-detail', kwargs={'slug': self.sa0.slug})

        # Non-Member can't delete
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        self.assertEqual(StreamAlias.objects.all().count(), 3)
        self.assertEqual(StreamAliasTap.objects.all().count(), 5)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAlias.objects.filter(pk=self.sa0.id).count(), 1)

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(StreamAlias.objects.all().count(), 3)
        self.assertEqual(StreamAliasTap.objects.all().count(), 5)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAlias.objects.filter(pk=self.sa0.id).count(), 1)

        # Permissions are required to delete stream alias
        membership = self.o2.register_user(self.u3, role='m1')
        membership.permissions['can_manage_stream_aliases'] = False
        membership.save()

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(StreamAlias.objects.all().count(), 3)
        self.assertEqual(StreamAliasTap.objects.all().count(), 5)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 44)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamAlias.objects.filter(pk=self.sa0.id).count(), 1)

        self.client.logout()

    def testFilter(self):
        url = reverse('streamalias-list')

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        o4 = Org.objects.create_org(name='Org 4', created_by=self.u2)
        sa3 = StreamAlias.objects.create(
            name='new alias',
            org=o4,
            created_by=self.u2,
        )

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 3)

        resp = self.client.get(url+'?org={}'.format(self.o2.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        resp = self.client.get(url+'?org={}'.format(o4.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['org'], o4.slug)

        self.client.logout()
