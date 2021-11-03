import datetime
import os
from unittest import mock
import dateutil.parser

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.test import Client

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.reverse import reverse

from apps.physicaldevice.models import Device
from apps.utils.data_mask.mask_utils import set_data_mask
from apps.stream.models import StreamVariable, StreamId
from apps.streamalias.models import StreamAlias, StreamAliasTap
from apps.streamfilter.models import *
from apps.utils.gid.convert import *
from apps.utils.test_util import TestMixin
from apps.utils.utest.utils.alias_utils import TestStreamAliasHelper
from apps.vartype.models import VarType
from apps.utils.timezone_utils import str_utc
from apps.datablock.models import DataBlock

from ..models import *

user_model = get_user_model()


def full_path(filename):
    module_path = os.path.dirname(__file__)
    return os.path.join(module_path, 'fixture-data', filename)


class StreamEventAPITests(TestMixin, TestStreamAliasHelper, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=1,
        )
        self.v2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p2, created_by=self.u3, lid=2,
        )
        self.v3 = StreamVariable.objects.create_variable(
            name='Var C', project=self.p1, created_by=self.u2, lid=3,
        )
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)
        StreamId.objects.create_after_new_device(self.pd1)
        StreamId.objects.create_after_new_device(self.pd2)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()
        self.s2 = StreamId.objects.filter(variable=self.v2).first()
        self.s3 = StreamId.objects.filter(variable=self.v3).first()
        self.var_type = VarType.objects.create(
            name='Accelerometer',
            storage_units_full='Object',
            created_by=self.u1
        )

        if cache:
            cache.clear()

    def tearDown(self):
        StreamFilterAction.objects.all().delete()
        StreamFilterTrigger.objects.all().delete()
        StreamFilter.objects.all().delete()
        StreamEventData.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testFilterAccess(self):
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        s = self.pd1.streamids.first()
        pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u2)
        db1 = DataBlock.objects.create(org=self.o2, title='test1', device=pd1, block=1, created_by=self.u2)
        pd2.active = False
        pd2.save()
        s1 = StreamId.objects.create_stream(project=self.p1, device=pd1, variable=self.v1, created_by=self.u2)
        s2 = StreamId.objects.create_stream(project=self.p2, device=pd2, variable=self.v1, created_by=self.u2)
        s3 = StreamId.objects.clone_into_block(s1, block=db1)
        self.assertIsNone(s3.project)
        data1 = StreamEventData.objects.create(
            id=5,
            timestamp=t0,
            device_timestamp=10,
            stream_slug=s1.slug,
            streamer_local_id=1,
        )
        data2 = StreamEventData.objects.create(
            id=6,
            timestamp=t0,
            device_timestamp=11,
            stream_slug=s2.slug,
            streamer_local_id=2,
        )
        data3 = StreamEventData(
            id=7,
            timestamp=t0,
            device_timestamp=11,
            stream_slug=s3.slug,
            streamer_local_id=3,
        )
        data3.deduce_slugs_from_stream_id()
        data3.save()
        # Hack to emulate archiving, which blanks the project_slug
        StreamEventData.objects.filter(stream_slug=s3.slug).update(project_slug='')

        list_url = reverse('streameventdata-list')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(list_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(list_url+'?staff=1', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(list_url+'?staff=1&filter={}'.format(s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.get(list_url+'?staff=1&filter={}'.format(s3.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

        # Staff has access to all
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(list_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(list_url+'?staff=1', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(list_url+'?filter={}'.format(s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.get(list_url+'?filter={}'.format(s2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(list_url+'?staff=1&filter={}'.format(s2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(list_url+'?filter={}'.format(s3.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.get(list_url+'?filter={}&lastn=-1'.format(s3.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(list_url+'?filter={}&lastn=20000000000'.format(s3.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(list_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(list_url+'?staff=1', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(list_url+'?filter={}'.format(s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(list_url+'?filter={}'.format(s2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.get(list_url+'?filter={}'.format(s3.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        self.client.logout()

    def testSreamAliasAccess(self):
        url = reverse('streameventdata-list')

        ts = dateutil.parser.parse('2016-09-28T10:00:00Z')

        d0 = StreamEventData.objects.create(
            timestamp=ts,
            device_timestamp=10,
            stream_slug=self.s1.slug,
            streamer_local_id=100,
        )
        d1 = StreamEventData.objects.create(
            timestamp=ts + datetime.timedelta(seconds=10),
            device_timestamp=20,
            stream_slug=self.s1.slug,
            streamer_local_id=101,
        )
        d2 = StreamEventData.objects.create(
            timestamp=ts + datetime.timedelta(seconds=20),
            device_timestamp=30,
            stream_slug=self.s1.slug,
            streamer_local_id=102,
        )
        d3 = StreamEventData.objects.create(
            timestamp=ts + datetime.timedelta(seconds=30),
            device_timestamp=40,
            stream_slug=self.s1.slug,
            streamer_local_id=103,
        )
        d4 = StreamEventData.objects.create(
            timestamp=ts + datetime.timedelta(seconds=20),
            stream_slug=self.s3.slug,
            streamer_local_id=104,
        )
        d5 = StreamEventData.objects.create(
            timestamp=ts + datetime.timedelta(seconds=25),
            stream_slug=self.s3.slug,
            streamer_local_id=105,
        )
        d6 = StreamEventData.objects.create(
            timestamp=ts + datetime.timedelta(seconds=25),
            stream_slug=self.s2.slug,
            streamer_local_id=106,
        )

        sa1 = StreamAlias.objects.create(
            name='some alias',
            org=self.o2,
            created_by=self.u2,
        )
        StreamAliasTap.objects.create(
            alias=sa1,
            timestamp=ts + datetime.timedelta(seconds=26),
            stream=self.s1,
            created_by=self.u2
        )
        StreamAliasTap.objects.create(
            alias=sa1,
            timestamp=ts + datetime.timedelta(seconds=5),
            stream=self.s1,
            created_by=self.u2
        )
        StreamAliasTap.objects.create(
            alias=sa1,
            timestamp=ts + datetime.timedelta(seconds=20),
            stream=self.s3,
            created_by=self.u2
        )
        sa2 = StreamAlias.objects.create(
            name='alias for o3',
            org=self.o3,
            created_by=self.u3,
        )
        StreamAliasTap.objects.create(
            alias=sa2,
            timestamp=ts + datetime.timedelta(seconds=20),
            stream=self.s2,
            created_by=self.u2
        )

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url+'?staff=1&filter={}'.format(sa1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 4)

        response = self.client.get(url+'?staff=1&filter={}'.format(sa2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url+'?staff=1&filter={}'.format(sa1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 4)

        response = self.client.get(url+'?staff=1&filter={}'.format(sa2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url+'?staff=1&filter={}'.format(sa1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url+'?staff=1&filter={}'.format(sa2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

    def testFilterNoStreamIdAccess(self):
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        s = self.pd1.streamids.first()
        pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u2)
        db1 = DataBlock.objects.create(org=self.o2, title='test1', device=pd1, block=1, created_by=self.u2)
        pd2.active = False
        pd2.save()

        s1 = IOTileStreamSlug()
        s1.from_parts(project=pd1.project.slug, device=pd1.slug, variable='5a09')

        s_no_project = IOTileStreamSlug()
        s_no_project.from_parts(project=0, device=pd1.slug, variable='5a09')

        s_no_device = IOTileStreamSlug()
        s_no_device.from_parts(project=pd1.project.slug, device=0, variable='5a09')

        StreamEventData.objects.create(
            id=5,
            timestamp=t0,
            device_timestamp=10,
            stream_slug=str(s1),
            streamer_local_id=1,
        )
        StreamEventData.objects.create(
            id=6,
            timestamp=t0+datetime.timedelta(hours=1),
            device_timestamp=11,
            stream_slug=str(s1),
            streamer_local_id=2,
        )
        StreamEventData.objects.create(
            id=7,
            timestamp=t0+datetime.timedelta(hours=2),
            device_timestamp=12,
            stream_slug=str(s_no_project),
            streamer_local_id=2,
        )
        StreamEventData.objects.create(
            id=8,
            timestamp=t0+datetime.timedelta(hours=3),
            device_timestamp=13,
            stream_slug=str(s_no_device),
            streamer_local_id=2,
        )
        list_url = reverse('streameventdata-list')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(list_url+'?filter={}'.format(s1), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        response = self.client.get(list_url+'?filter={}'.format(s_no_device), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.get(list_url+'?filter={}'.format(s_no_project), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(pd1.org.has_permission(self.u2, 'can_read_stream_data'))

        response = self.client.get(list_url+'?filter={}'.format(s1), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertFalse(pd1.org.has_permission(self.u3, 'can_read_stream_data'))

        response = self.client.get(list_url+'?filter={}'.format(s1), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(list_url+'?filter={}'.format(s_no_device), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(list_url+'?filter={}'.format(s_no_project), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        self.client.logout()

    def testGet(self):
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        s = self.pd1.streamids.first()
        data = StreamEventData(
            id=5,
            timestamp=t0,
            device_timestamp=10,
            stream_slug=s.slug,
            streamer_local_id=1,
        )
        data.deduce_slugs_from_stream_id()
        data.save()
        url = reverse('streameventdata-detail', kwargs={'pk': data.id})

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['id'], data.id)
        self.assertEqual(deserialized['stream'], data.stream_slug)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.p1.has_access(self.u2))

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['id'], data.id)
        self.assertEqual(deserialized['stream'], data.stream_slug)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testGetLastN(self):

        url = reverse('streameventdata-list')

        StreamEventData.objects.create(
            stream_slug=self.s1.slug,
            timestamp=timezone.now(),
            streamer_local_id=5
        )
        StreamEventData.objects.create(
            stream_slug=self.s1.slug,
            timestamp=timezone.now(),
            streamer_local_id=6
        )
        StreamEventData.objects.create(
            stream_slug=self.s1.slug,
            timestamp=timezone.now(),
            streamer_local_id=7
        )
        StreamEventData.objects.create(
            stream_slug=self.s2.slug,
            timestamp=timezone.now(),
            streamer_local_id=8
        )
        StreamEventData.objects.create(
            stream_slug=self.s2.slug,
            timestamp=timezone.now(),
            streamer_local_id=9
        )

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url+'?staff=1&filter={}'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url+'?staff=1&filter={}&lastn=1'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['streamer_local_id'], 7)

        response = self.client.get(url+'?staff=1&filter={}&lastn=2'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)
        self.assertEqual(deserialized['results'][0]['streamer_local_id'], 6)
        self.assertEqual(deserialized['results'][1]['streamer_local_id'], 7)

        response = self.client.get(url+'?staff=1&filter={}&lastn=-1'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(url+'?staff=1&filter={}&lastn=20000000000'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.logout()

    def testGetWithFilter(self):
        url = reverse('streameventdata-list')

        d0 = StreamEventData.objects.create(
            stream_slug=self.s1.slug,
            device_timestamp=10,
            streamer_local_id=100,
            timestamp=timezone.now(),
        )
        d1 = StreamEventData.objects.create(
            stream_slug=self.s1.slug,
            device_timestamp=11,
            streamer_local_id=101,
            timestamp=timezone.now(),
        )
        d2 = StreamEventData.objects.create(
            stream_slug=self.s1.slug,
            device_timestamp=12,
            streamer_local_id=102,
            timestamp=timezone.now(),
        )
        d3 = StreamEventData.objects.create(
            stream_slug=self.s1.slug,
            device_timestamp=13,
            streamer_local_id=103,
            timestamp=timezone.now(),
        )
        StreamEventData.objects.create(
            stream_slug=self.s2.slug,
            timestamp=timezone.now(),
        )
        StreamEventData.objects.create(
            stream_slug=self.s2.slug,
            timestamp=timezone.now(),
        )

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url+'?staff=1&filter={}'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 4)

        response = self.client.get(url+'?staff=1&filter={}'.format(self.s2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        response = self.client.get(url+'?staff=1&filter={}'.format(self.pd2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        response = self.client.get(url+'?staff=1&filter={}'.format(self.v2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        # Old version of range, with _0 and _1 suffixes
        response = self.client.get(url+'?staff=1&filter={0}&id_0={1}'.format(self.s1.slug, d1.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url+'?staff=1&filter={0}&id_0={1}&id_1={1}'.format(self.s1.slug, d1.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.get(url+'?staff=1&filter={0}&streamer_id_0={1}'.format(self.s1.slug, d1.streamer_local_id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url+'?staff=1&filter={0}&streamer_id_0={1}&streamer_id_0={2}'.format(self.s1.slug, d1.streamer_local_id, d2.streamer_local_id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        # New version of range, with _min and _max suffixes
        response = self.client.get(url+'?staff=1&filter={0}&id_min={1}'.format(self.s1.slug, d1.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url+'?staff=1&filter={0}&id_min={1}&id_max={1}'.format(self.s1.slug, d1.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.get(url+'?staff=1&filter={0}&streamer_ts_min={1}'.format(self.s1.slug, d1.device_timestamp), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url+'?staff=1&filter={0}&streamer_id_min={1}'.format(self.s1.slug, d1.streamer_local_id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url+'?staff=1&filter={0}&streamer_ts_min={1}&streamer_ts_max={2}'.format(self.s1.slug, d1.device_timestamp, d2.device_timestamp), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        response = self.client.get(url+'?staff=1&filter={0}&streamer_id_min={1}&streamer_id_max={2}'.format(self.s1.slug, d1.streamer_local_id, d2.streamer_local_id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        self.client.logout()

    def testGetBadPk(self):
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        s = self.pd1.streamids.first()
        data = StreamEventData(
            id=5,
            timestamp=t0,
            device_timestamp=10,
            stream_slug=s.slug,
            streamer_local_id=1,
        )
        data.deduce_slugs_from_stream_id()
        data.save()
        # Illegal record ID
        url = '/api/v1/event/{}/'.format(data.stream_slug)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.logout()

    @mock.patch('apps.streamevent.helpers.upload_json_data_from_object')
    def testBasicPost(self, mock_upload_json):
        mock_upload_json.return_value = True
        url = reverse('streameventdata-list')
        payload = {
            'stream': self.s1.slug,
            'timestamp': timezone.now(),
            'data': {
                'foo': 5,
                'bar': 'abc'
            }
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamEventData.objects.count(), 1)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['project'], self.s1.project.slug)
        self.assertEqual(deserialized['device'], self.s1.device.slug)
        self.assertEqual(deserialized['variable'], self.s1.variable.slug)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamEventData.objects.count(), 2)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['project'], self.s1.project.slug)
        self.assertEqual(deserialized['device'], self.s1.device.slug)
        self.assertEqual(deserialized['variable'], self.s1.variable.slug)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testIllegalPost(self):
        url = reverse('streameventdata-list')
        payload = {
            'timestamp': timezone.now(),
            'data': {
                'foo': 5,
                'bar': 'abc'
            }
        }

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(url, [payload,payload], format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.logout()

    @mock.patch('apps.streamevent.helpers.upload_json_data_from_object')
    def testNoStreamIdPost(self, mock_upload_json):
        mock_upload_json.return_value = True
        url = reverse('streameventdata-list')

        pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        db1 = DataBlock.objects.create(org=self.o2, title='test1', device=pd1, block=1, created_by=self.u2)

        s_no_project = IOTileStreamSlug()
        s_no_project.from_parts(project=0, device=pd1.slug, variable='5a09')

        s_no_device = IOTileStreamSlug()
        s_no_device.from_parts(project=pd1.project.slug, device=0, variable='5a09')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            'stream': str(s_no_project),
            'timestamp': timezone.now(),
            'streamer_local_id': 2,
            'data': {
                'foo': 5,
                'bar': 'abc'
            }
        }

        self.assertEqual(StreamEventData.objects.filter(device_slug=pd1.slug).count(), 0)
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamEventData.objects.filter(device_slug=pd1.slug).count(), 1)

        payload = {
            'stream': str(s_no_device),
            'timestamp': timezone.now(),
            'streamer_local_id': 2,
            'data': {
                'foo': 5,
                'bar': 'abc'
            }
        }

        self.assertEqual(StreamEventData.objects.filter(project_slug=pd1.project.slug).count(), 0)
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamEventData.objects.filter(project_slug=pd1.project.slug).count(), 1)

        self.client.logout()

    @mock.patch('apps.streamevent.helpers.upload_json_data_from_object')
    def testBasicMultiPost(self, mock_upload_json):
        mock_upload_json.return_value = True
        url = reverse('streameventdata-list')
        t1 = timezone.now()
        payload = [
            {
                'stream': self.s1.slug,
                'timestamp': t1,
                'streamer_local_id': 2,
                'data': {
                    'foo': 5,
                    'bar': 'abc'
                }
            },
            {
                'stream': self.s1.slug,
                'timestamp': t1 + datetime.timedelta(hours=1),
                'streamer_local_id': 3,
                'data': {
                    'foo': 6,
                    'bar': 'xyz'
                }
            }
        ]

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamEventData.objects.count(), 2)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)
        first = StreamEventData.objects.first()
        self.assertEqual(first.streamer_local_id, 2)
        last = StreamEventData.objects.last()
        self.assertEqual(last.streamer_local_id, 3)

        self.client.logout()

    @mock.patch('apps.streamevent.helpers.upload_json_data_from_object')
    def testPostDisableStream(self, mock_upload_json):
        mock_upload_json.return_value = True
        url = reverse('streameventdata-list')
        t1 = timezone.now()
        self.s1.enabled = False
        self.s1.save()
        payload = [
            {
                'stream': self.s1.slug,
                'timestamp': t1,
                'streamer_local_id': 2,
                'data': {
                    'foo': 5,
                    'bar': 'abc'
                }
            },
            {
                'stream': self.s1.slug,
                'timestamp': t1 + datetime.timedelta(hours=1),
                'streamer_local_id': 3,
                'data': {
                    'foo': 6,
                    'bar': 'xyz'
                }
            }
        ]

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(StreamEventData.objects.count(), 0)

        self.s1.enabled = True
        self.s1.save()

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamEventData.objects.count(), 2)

        self.client.logout()

    @mock.patch('apps.streamevent.api_views.upload_json_data_from_object')
    def testBasicPatch(self, mock_upload_json):
        mock_upload_json.return_value = True
        post_url = reverse('streameventdata-list')

        payload = {
            'stream': self.s1.slug,
            'timestamp': timezone.now()
        }

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(post_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamEventData.objects.count(), 1)
        deserialized = json.loads(response.content.decode())
        event_id = deserialized['id']
        self.assertFalse(deserialized['has_raw_data'])

        patch_url = reverse('streameventdata-detail', kwargs={'pk': event_id})

        payload = {
            'data': {
                'foo': 5,
                'bar': 'abc'
            }
        }

        response = self.client.patch(patch_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertTrue(deserialized['has_raw_data'])

        event = StreamEventData.objects.get(id=deserialized['id'])
        self.assertTrue((event.has_raw_data))

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.patch(patch_url, payload, format='json')

        payload = {
            'data': {
                'foo': 6,
                'bar': 'def'
            }
        }

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(StreamEventData.objects.count(), 1)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertFalse(self.s1.org.has_permission(self.u3, 'can_create_stream_data'))

        response = self.client.patch(patch_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.s1.org.register_user(self.u3, role='m1')
        self.assertTrue(self.s1.org.has_permission(self.u3, 'can_create_stream_data'))
        response = self.client.patch(patch_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.logout()


    def testExtraDataGet(self):
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        s = self.pd1.streamids.first()
        data = StreamEventData(
            id=5,
            timestamp=t0,
            device_timestamp=10,
            stream_slug=s.slug,
            streamer_local_id=1,
        )
        data.deduce_slugs_from_stream_id()
        data.set_summary_value('Var1', 'Val1')
        data.set_summary_value('Var2', 2)
        data.set_summary_value('Var3', True)
        data.save()
        url = reverse('streameventdata-detail', kwargs={'pk': data.id})

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['extra_data']['Var1'], 'Val1')
        self.assertEqual(deserialized['extra_data']['Var2'], 2)
        self.assertEqual(deserialized['extra_data']['Var3'], True)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.p1.has_access(self.u2))

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['extra_data']['Var1'], 'Val1')
        self.assertEqual(deserialized['extra_data']['Var2'], 2)
        self.assertEqual(deserialized['extra_data']['Var3'], True)

        self.client.logout()

    @mock.patch('apps.streamevent.helpers.upload_json_data_from_object')
    def testExtraDataPost(self, mock_upload_json):
        mock_upload_json.return_value = True
        url = reverse('streameventdata-list')
        payload = {
            'stream': self.s1.slug,
            'timestamp': timezone.now(),
            'data': {
                'foo': 5,
                'bar': 'abc'
            },
            'extra_data': {
                'v1': 'foo',
                'v2': 2,
                'v3': True
            }
        }

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        event = StreamEventData.objects.get(pk=deserialized['id'])
        self.assertIsNotNone(event.extra_data)
        self.assertIsNotNone(event.summary)
        self.assertTrue(isinstance(event.summary, dict))
        self.assertEqual(event.get_summary_value('v1'), 'foo')
        self.assertEqual(event.summary['v1'], 'foo')
        self.assertEqual(event.summary['v2'], 2)
        self.assertEqual(event.summary['v3'], True)

        payload = {
            'stream': self.s1.slug,
            'timestamp': timezone.now(),
            'data': {
                'foo': 5,
                'bar': 'abc'
            },
            'extra_data': [ 'v1', 'v2']
        }
        response = self.client.post(url, data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        payload['extra_data'] = 5
        response = self.client.post(url, data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        payload['extra_data'] = None
        response = self.client.post(url, data=payload, format='json')
        # This field may not be null.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch("apps.streamfilter.actions.cus_action.action._sns_text_based_notification")
    @mock.patch('apps.streamevent.helpers.upload_json_data_from_object')
    def testFilterPost(self, mock_upload_json, mock_sns):
        mock_upload_json.return_value = True
        url = reverse('streameventdata-list')
        payload = {
            'stream': self.s1.slug,
            'timestamp': timezone.now(),
            'data': {
                'foo': 5,
                'bar': 'abc'
            }
        }

        f = StreamFilter.objects.create_filter_from_streamid(name='test',
                                                             input_stream=self.s1,
                                                             created_by=self.u1)
        state = State.objects.create(label="state1", filter=f, created_by=self.u2)
        a = StreamFilterAction.objects.create(
            type="cus", created_by=self.u1, extra_payload={"sns_topic": "dummy_topic"}, on='entry', state=state
        )
        transition = StateTransition.objects.create(src=state, dst=state, filter=f, created_by=self.u2)
        t = StreamFilterTrigger.objects.create(operator="bu", threshold=None, created_by=self.u1, filter=f, transition=transition)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamEventData.objects.count(), 1)
        event = StreamEventData.objects.all().first()
        sns_payload = {
            "uuid": str(event.uuid),
            "project": event.project_slug,
            "device": event.device_slug,
            "stream": event.stream_slug,
            "timestamp": str_utc(event.timestamp),
            "bucket": event.s3bucket,
            "key": event.s3key
        }
        mock_sns.assert_called_with("dummy_topic", json.dumps(sns_payload))
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['project'], self.s1.project.slug)
        self.assertEqual(deserialized['device'], self.s1.device.slug)
        self.assertEqual(deserialized['variable'], self.s1.variable.slug)

        self.client.logout()

    @mock.patch("apps.streamfilter.actions.cus_action.action._sns_text_based_notification")
    @mock.patch('apps.streamevent.helpers.upload_json_data_from_object')
    def testFilterMultiplePost(self, mock_upload_json, mock_sns):
        url = reverse('streameventdata-list')
        t1 = timezone.now()
        payload = [
            {
                'stream': self.s1.slug,
                'timestamp': t1,
                'streamer_local_id': 2,
                'data': {
                    'foo': 5,
                    'bar': 'abc'
                }
            },
            {
                'stream': self.s1.slug,
                'timestamp': t1 + datetime.timedelta(hours=1),
                'streamer_local_id': 3,
                'data': {
                    'foo': 6,
                    'bar': 'xyz'
                }
            }
        ]
        mock_upload_json.return_value = True

        f = StreamFilter.objects.create_filter_from_streamid(name='test',
                                                             input_stream=self.s1,
                                                             created_by=self.u1)
        state = State.objects.create(label="state1", filter=f, created_by=self.u2)
        a = StreamFilterAction.objects.create(
            type="cus", created_by=self.u1, extra_payload={"sns_topic": "dummy_topic"}, on='entry', state=state
        )
        transition = StateTransition.objects.create(src=state, dst=state, filter=f, created_by=self.u2)
        t = StreamFilterTrigger.objects.create(operator="bu", threshold=None, created_by=self.u1, filter=f, transition=transition)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamEventData.objects.count(), 2)

        self.assertEqual(mock_sns.call_count, 2)

        self.client.logout()

    @mock.patch('apps.streamevent.helpers.upload_json_data_from_object')
    def testMsgPackMultiPost(self, mock_upload_json):
        url = reverse('streameventdata-list')
        t1 = timezone.now()
        payload = [
            {
                'stream': self.s1.slug,
                'timestamp': str_utc(t1),
                'streamer_local_id': 2,
                'data': {
                    'foo': 5,
                    'bar': 'abc'
                }
            },
            {
                'stream': self.s1.slug,
                'timestamp': str_utc(t1 + datetime.timedelta(hours=1)),
                'streamer_local_id': 3,
                'data': {
                    'foo': 6,
                    'bar': 'xyz'
                }
            }
        ]
        mock_upload_json.return_value = True

        import msgpack
        packed = msgpack.packb(payload)

        c = Client()
        c.login(email='user1@foo.com', password='pass')

        response = c.post(url, packed, content_type='application/msgpack')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamEventData.objects.count(), 2)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)
        first = StreamEventData.objects.first()
        self.assertEqual(first.streamer_local_id, 2)
        last = StreamEventData.objects.last()
        self.assertEqual(last.streamer_local_id, 3)

        c.logout()

    def testNoData(self):
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        s = self.pd1.streamids.first()
        data = StreamEventData(
            id=5,
            timestamp=t0,
            device_timestamp=10,
            stream_slug=s.slug,
            streamer_local_id=1,
        )
        data.deduce_slugs_from_stream_id()
        data.save()
        self.assertIsNone(data.s3key)
        self.assertFalse(data.has_raw_data)
        url = reverse('streameventdata-data', kwargs={'pk': data.id})

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

    def testGetBlock(self):
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        s = self.pd1.streamids.first()
        pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        pd2 = Device.objects.create_device(project=self.p1, label='d2', template=self.dt1, created_by=self.u2)
        db1 = DataBlock.objects.create(org=self.o2, title='test1', device=pd1, block=1, created_by=self.u2)
        db2 = DataBlock.objects.create(org=self.o2, title='test2', device=pd2, block=1, created_by=self.u2)
        pd2.active = False
        pd2.save()
        s1 = StreamId.objects.create_stream(project=self.p1, device=pd1, variable=self.v1, created_by=self.u2)
        s2 = StreamId.objects.create_stream(project=self.p1, device=pd2, variable=self.v1, created_by=self.u2)
        s3 = StreamId.objects.clone_into_block(s1, block=db1)
        s4 = StreamId.objects.clone_into_block(s2, block=db2)
        self.assertIsNone(s3.project)
        self.assertIsNone(s4.project)
        data1 = StreamEventData.objects.create(
            id=5,
            timestamp=t0,
            device_timestamp=10,
            stream_slug=s1.slug,
            streamer_local_id=1,
        )
        data2 = StreamEventData.objects.create(
            id=6,
            timestamp=t0,
            device_timestamp=11,
            stream_slug=s2.slug,
            streamer_local_id=2,
        )
        data3 = StreamEventData(
            id=7,
            timestamp=t0,
            device_timestamp=11,
            stream_slug=s3.slug,
            streamer_local_id=3,
        )
        data3.deduce_slugs_from_stream_id()
        data3.save()
        data4 = StreamEventData(
            id=8,
            timestamp=t0,
            device_timestamp=11,
            stream_slug=s4.slug,
            streamer_local_id=4,
        )
        data4.deduce_slugs_from_stream_id()
        data4.save()
        # Hack to emulate archiving, which blanks the project_slug
        StreamEventData.objects.filter(stream_slug__in=[s3.slug, s4.slug]).update(project_slug='')

        url1 = reverse('streameventdata-detail', kwargs={'pk': data1.id})
        url2 = reverse('streameventdata-detail', kwargs={'pk': data2.id})
        url3 = reverse('streameventdata-detail', kwargs={'pk': data3.id})
        url4 = reverse('streameventdata-detail', kwargs={'pk': data4.id})
        list_url = reverse('streameventdata-list')


        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        # Staff can retrieve any record
        for url in [url1, url2, url3, url4]:
            resp = self.client.get(url, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

        response = self.client.get(list_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(list_url+'?staff=1', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(list_url+'?staff=1&filter={}'.format(s3.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

        # Staff has access to all
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        for url in [url1, url2, url3, url4]:
            resp = self.client.get(url, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK, msg=url)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        for url in [url1, url2, url3, url4]:
            resp = self.client.get(url, format='json')
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testDateTimeFormat(self):
        url = reverse('streameventdata-list')

        dt1 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        dt2 = dateutil.parser.parse('2016-09-28T20:00:00-08:00')
        dt3 = dateutil.parser.parse('2016-09-29T20:00:00+03:00')

        data1 = StreamEventData.objects.create(
            timestamp=dt1,
            device_timestamp=10,
            stream_slug=self.s1.slug,
            streamer_local_id=1,
        )
        data2 = StreamEventData.objects.create(
            timestamp=dt2,
            device_timestamp=11,
            stream_slug=self.s1.slug,
            streamer_local_id=2,
        )
        data3 = StreamEventData.objects.create(
            timestamp=dt3,
            device_timestamp=12,
            stream_slug=self.s1.slug,
            streamer_local_id=3,
        )

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url+'?filter={}'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)
        self.assertEqual(deserialized['results'][0]['timestamp'], '2016-09-28T10:00:00Z')
        self.assertEqual(deserialized['results'][1]['timestamp'], '2016-09-29T04:00:00Z')
        self.assertEqual(deserialized['results'][2]['timestamp'], '2016-09-29T17:00:00Z')

        payload = {
            'stream': self.s1.slug,
            'timestamp': '2017-09-28T10:00:00Z',
            'streamer_local_id': 10,
            'extra_data': {
                'foo': 5,
                'bar': 'abc'
            }
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['timestamp'], '2017-09-28T10:00:00Z')

        payload = {
            'stream': self.s1.slug,
            'timestamp': '2017-09-28T20:00:00-08:00',
            'streamer_local_id': 10,
            'extra_data': {
                'foo': 5,
                'bar': 'abc'
            }
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['timestamp'], '2017-09-29T04:00:00Z')

        payload = {
            'stream': self.s1.slug,
            'timestamp': '2017-09-28T20:00:00+00:00',
            'streamer_local_id': 10,
            'extra_data': {
                'foo': 5,
                'bar': 'abc'
            }
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['timestamp'], '2017-09-28T20:00:00Z')

        payload = {
            'stream': self.s1.slug,
            'timestamp': '2017-09-28T20:00:00',
            'streamer_local_id': 10,
            'extra_data': {
                'foo': 5,
                'bar': 'abc'
            }
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['timestamp'], '2017-09-28T20:00:00Z')

        self.client.logout()

    def testFilterErrors(self):
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        s = self.pd1.streamids.first()
        pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        s1 = StreamId.objects.create_stream(project=self.p1, device=pd1, variable=self.v1, created_by=self.u2)
        data1 = StreamEventData.objects.create(
            id=5,
            timestamp=t0,
            device_timestamp=10,
            stream_slug=s1.slug,
            streamer_local_id=1,
        )
        data2 = StreamEventData.objects.create(
            id=6,
            timestamp=t0,
            device_timestamp=11,
            stream_slug=s1.slug,
            streamer_local_id=2,
        )
        data3 = StreamEventData.objects.create(
            id=7,
            timestamp=t0,
            device_timestamp=12,
            stream_slug=s1.slug,
            streamer_local_id=3,
            extra_data = {
                "end": 355,
                "start": 351,
                "error": "....: RawPacketFromat length (<LLLL=5 - 1) is not the same as packet size (3)"
            }
        )

        list_url = reverse('streameventdata-list')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(list_url+'?staff=1&filter={}'.format(s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)
        for item in deserialized['results']:
            self.assertTrue(item['id'] in [5, 6])

        response = self.client.get(list_url+'?staff=1&filter={}&with_errors=1'.format(s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)
        for item in deserialized['results']:
            self.assertTrue(item['id'] in [5, 6, 7])

        self.client.logout()

    @mock.patch('apps.streamevent.helpers.StreamEventDataBuilderHelper.process_serializer_data')
    def testProcessFilterCalledWithUserSlug(self, mock_process_serializer_data):
        url = reverse('streameventdata-list')
        payload = {
            'stream': self.s1.slug,
            'timestamp': timezone.now(),
            'data': {
                'foo': 5,
                'bar': 'abc'
            }
        }

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        self.client.post(url, payload, format='json')
        mock_process_serializer_data.assert_called_with(mock.ANY, user_slug=self.u1.slug)

    @mock.patch('apps.streamevent.helpers.upload_blob')
    @mock.patch('apps.streamevent.helpers.upload_json_data_from_object')
    def testRawFilePost(self, mock_upload_json, mock_upload_blob):
        url = '/api/v1/event/upload/'
        payload = {
            'stream': self.s1.slug,
            'timestamp': timezone.now(),
            'streamer_local_id': 1,
            'data': {
                'foo': 5,
                'bar': 'abc'
            }
        }
        mock_upload_json.return_value = True

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        # response = self.client.post(url, payload, format='json')
        # self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        # Illegal to upload with data
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        del(payload['data'])

        test_filename = full_path('sample1.json')

        with open(test_filename, 'rb') as fp:
            # mock_upload_blob.return_value = fp
            mock_upload_json.return_value = True
            payload['file'] = fp
            response = self.client.post(url, payload, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            fp.close()
        self.assertEqual(StreamEventData.objects.count(), 1)
        event = StreamEventData.objects.first()
        self.assertEqual(event.project_slug, self.s1.project.slug)
        self.assertEqual(event.device_slug, self.s1.device.slug)
        self.assertEqual(event.variable_slug, self.s1.variable.slug)
        self.assertEqual(event.streamer_local_id, 1)
        self.assertEqual(event.ext, 'json')
        self.assertEqual(event.format_version, 2)
        self.assertTrue(event.has_raw_data)
        self.assertIsNone(event.extra_data)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            'stream': self.s1.slug,
            'timestamp': timezone.now(),
            'streamer_local_id': 2,
            'encoded_extra_data': json.dumps({ 'a': 4})
        }
        test_filename = full_path('sample2.json.gz')

        with open(test_filename, 'rb') as fp:
            # mock_upload_blob.return_value = fp
            payload['file'] = fp
            response = self.client.post(url, payload, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            fp.close()
        self.assertEqual(StreamEventData.objects.count(), 2)
        event = StreamEventData.objects.last()
        self.assertEqual(event.streamer_local_id, 2)
        self.assertEqual(event.ext, 'json.gz')
        self.assertIsNotNone(event.extra_data)
        self.assertTrue('a' in event.extra_data)
        self.assertEqual(event.extra_data['a'], 4)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        test_filename = full_path('sample1.json')

        with open(test_filename, 'rb') as fp:
            # mock_upload_blob.return_value = fp
            payload['file'] = fp
            response = self.client.post(url, payload, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            fp.close()

        self.client.logout()

    def testGetWithStartEndDateWithDeviceMask(self):
        base_url = reverse('streameventdata-list')
        base_url += '?staff=1&filter={}'.format(self.s1.slug)

        dt1 = dateutil.parser.parse('2017-09-28T10:00:00Z')
        dt2 = dateutil.parser.parse('2017-09-28T11:00:00Z')
        dt3 = dateutil.parser.parse('2017-09-30T10:00:00Z')
        dt4 = dateutil.parser.parse('2017-09-30T10:10:00Z')
        dt5 = dateutil.parser.parse('2017-09-30T10:20:00Z')

        set_data_mask(self.pd1, '2017-09-28T10:30:00Z', '2017-09-30T10:15:00Z', [], [], self.u1)

        StreamEventData.objects.create(
            id=6,
            timestamp=dt1,
            device_timestamp=11,
            stream_slug=self.s1.slug,
            streamer_local_id=2,
        )
        StreamEventData.objects.create(
            id=7,
            timestamp=dt2,
            device_timestamp=21,
            stream_slug=self.s1.slug,
            streamer_local_id=3,
        )
        StreamEventData.objects.create(
            id=8,
            timestamp=dt3,
            device_timestamp=31,
            stream_slug=self.s1.slug,
            streamer_local_id=4,
        )
        StreamEventData.objects.create(
            id=9,
            timestamp=dt4,
            device_timestamp=41,
            stream_slug=self.s1.slug,
            streamer_local_id=5,
        )
        StreamEventData.objects.create(
            id=10,
            timestamp=dt5,
            device_timestamp=51,
            stream_slug=self.s1.slug,
            streamer_local_id=6,
        )

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        url = base_url+'&mask=1'
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        url = base_url+'&start={}'.format('2017-09-28T11:00:00Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 4)

        url = base_url+'&start={}&mask=1'.format('2017-09-28T11:00:00Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        url = base_url+'&start={0}&end={1}&mask=1'.format('2017-09-28T11:00:00Z', '2017-09-30T10:00:10Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        url = base_url+'&start={0}&end={1}'.format('2017-09-28T9:00:00Z', '2017-09-30T15:00:10Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 5)

        url = base_url+'&start={0}&end={1}&mask=1'.format('2017-09-28T9:00:00Z', '2017-09-30T15:00:10Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        url = base_url+'&mask=1'
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        url = base_url+'&start={}'.format('2017-09-28T11:00:00Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 4)

        url = base_url+'&start={}&mask=1'.format('2017-09-28T11:00:00Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        url = base_url+'&start={0}&end={1}&mask=1'.format('2017-09-28T11:00:00Z', '2017-09-30T10:00:10Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        url = base_url+'&start={0}&end={1}'.format('2017-09-28T9:00:00Z', '2017-09-30T15:00:10Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 5)

        url = base_url+'&start={0}&end={1}&mask=1'.format('2017-09-28T9:00:00Z', '2017-09-30T15:00:10Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        self.client.logout()

    def testGetWithStreamAlias(self):
        url = reverse('streameventdata-list')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        ts = dateutil.parser.parse('2016-09-28T10:00:00Z')

        # Empty Stream Alias
        ######################

        sa2 = self.create_alias(self.u2, 'empty alias', self.o2)

        # if stream alias is empty, no data is returned
        response = self.client.get(url+'?staff=1&filter={}'.format(sa2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        d0 = StreamEventData.objects.create(
            timestamp=ts,
            device_timestamp=10,
            stream_slug=self.s1.slug,
            streamer_local_id=100,
        )
        d1 = StreamEventData.objects.create(
            timestamp=ts + datetime.timedelta(seconds=10),
            device_timestamp=20,
            stream_slug=self.s1.slug,
            streamer_local_id=101,
        )
        d2 = StreamEventData.objects.create(
            timestamp=ts + datetime.timedelta(seconds=20),
            device_timestamp=30,
            stream_slug=self.s1.slug,
            streamer_local_id=102,
        )
        d3 = StreamEventData.objects.create(
            timestamp=ts + datetime.timedelta(seconds=30),
            device_timestamp=40,
            stream_slug=self.s1.slug,
            streamer_local_id=103,
        )
        d4 = StreamEventData.objects.create(
            timestamp=ts + datetime.timedelta(seconds=20),
            stream_slug=self.s3.slug,
            streamer_local_id=104,
        )
        d5 = StreamEventData.objects.create(
            timestamp=ts + datetime.timedelta(seconds=25),
            stream_slug=self.s3.slug,
            streamer_local_id=105,
        )

        # Stream Alias w/ single Tap
        ##############################

        sa3 = self.create_alias(self.u2, 'alias w/ single tap', self.o2, [
            {
                'ts': ts + datetime.timedelta(seconds=20),
                'stream': self.s1,
            }
        ])

        response = self.client.get(url+'?staff=1&filter={}'.format(sa3.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        # check the results are as expected (order matters)
        results = deserialized['results']
        self.assertEqual(results[0]['timestamp'], '2016-09-28T10:00:20Z')
        self.assertEqual(results[0]['stream'], d2.stream_slug)
        self.assertEqual(results[0]['streamer_local_id'], d2.streamer_local_id)        
        self.assertEqual(results[1]['timestamp'], '2016-09-28T10:00:30Z')
        self.assertEqual(results[1]['stream'], d3.stream_slug)
        self.assertEqual(results[1]['streamer_local_id'], d3.streamer_local_id)

        # Stream Alias w/ multiple Taps
        #################################

        sa1 = self.create_alias(self.u2, 'some alias', self.o2, [
            {
                'ts': ts + datetime.timedelta(seconds=26),
                'stream': self.s1,
            },
            {
                'ts': ts + datetime.timedelta(seconds=5),
                'stream': self.s1,
            },
            {
                'ts': ts + datetime.timedelta(seconds=20),
                'stream': self.s3,
            },
        ])

        response = self.client.get(url+'?staff=1&filter={}'.format(sa1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 4)
        
        # check the results are as expected (order matters)
        results = deserialized['results']
        self.assertEqual(results[0]['timestamp'], '2016-09-28T10:00:10Z')
        self.assertEqual(results[0]['stream'], d1.stream_slug)
        self.assertEqual(results[0]['streamer_local_id'], d1.streamer_local_id)        
        self.assertEqual(results[1]['timestamp'], '2016-09-28T10:00:20Z')
        self.assertEqual(results[1]['stream'], d4.stream_slug)
        self.assertEqual(results[1]['streamer_local_id'], d4.streamer_local_id)
        self.assertEqual(results[2]['timestamp'], '2016-09-28T10:00:25Z')
        self.assertEqual(results[2]['stream'], d5.stream_slug)
        self.assertEqual(results[2]['streamer_local_id'], d5.streamer_local_id)        
        self.assertEqual(results[3]['timestamp'], '2016-09-28T10:00:30Z')
        self.assertEqual(results[3]['stream'], d3.stream_slug)
        self.assertEqual(results[3]['streamer_local_id'], d3.streamer_local_id)

        # Test Case no.1
        ##################

        # D1: /\/\/\/\/\/\               \/\/\/\/\
        # D2:             \/\/\/\/\|| NO EVENT FROM HERE
        # D3:      NO EVENT HERE ||\/\/\/|| NO EVENT FROM HERE
        #
        # M1: /\/\/\/\/\/\\/\/\/\/\
        # M2:                      \/\/\/\/\/\/\/\

        s1 = self.create_device_and_associated_stream('D1')
        s2 = self.create_device_and_associated_stream('D2')
        s3 = self.create_device_and_associated_stream('D3')
        # 5 hours
        self.fill_stream_with_events(s1, 600, ts, 30)
        # 3 hours
        self.fill_stream_with_events(s2, 360, ts, 30)
        # 30 minutes
        self.fill_stream_with_events(s3, 60, ts + datetime.timedelta(hours=3), 30)

        sa1 = self.create_alias(self.u3, 'M1', self.o3, [
            {
                'ts': ts,
                'stream': s1,
            },
            {
                'ts': ts + datetime.timedelta(hours=2),
                'stream': s2,
            },
        ])

        sa2 = self.create_alias(self.u3, 'M2', self.o3, [
            {
                'ts': ts + datetime.timedelta(hours=3),
                'stream': s3,
            },
            {
                'ts': ts + datetime.timedelta(minutes=210),
                'stream': s1,
            },
        ])

        response = self.client.get(url+'?staff=1&filter={}'.format(sa1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 360)
        results = deserialized['results']
        # assert results are ordered by timestamp
        self.assert_results_are_ordered_by_timestamp(results)

        self.assert_data_from_correct_stream(results, [
            {
                'start': ts,
                'end': ts + datetime.timedelta(hours=2),
                'stream': s1,
            },
            {
                'start': ts + datetime.timedelta(hours=2),
                'end': ts + datetime.timedelta(hours=3),
                'stream': s2,
            },
        ])

        response = self.client.get(url+'?staff=1&filter={}'.format(sa2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 240)
        results = deserialized['results']
        # assert results are ordered by timestamp
        self.assert_results_are_ordered_by_timestamp(results)

        self.assert_data_from_correct_stream(results, [
            {
                'start': ts + datetime.timedelta(hours=3),
                'end': ts + datetime.timedelta(minutes=210),
                'stream': s3,
            },
            {
                'start': ts + datetime.timedelta(minutes=210),
                'end': ts + datetime.timedelta(hours=5),
                'stream': s1,
            },
        ])

        # Test Case no.2
        ##################

        # D1: \/\/\/                  \/\/\/      \/\/\/
        # D2:                               \/\/\/
        # D3:  NO EVENT ||\/\/\/
        # D4:       \/\/\/      \/\/\/|| NO EVENT FROM HERE
        #
        # A1: \/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/
        # A2:                      /\/\/\/\/\/\/\/\/\/\/
        #
        # D1:
        # D2:       \/\/\/                  \/\/\/
        # D3:  NO EVENT ||            \/\/\/
        # D4:             \/\/\/\/\/\/|| NO EVENT FROM HERE
        #
        # A3:       \/\/\/\/\/\/\/\/\/\/\/\/\/\/\/
        #
        s1 = self.create_device_and_associated_stream('D1')
        s2 = self.create_device_and_associated_stream('D2')
        s3 = self.create_device_and_associated_stream('D3')
        s4 = self.create_device_and_associated_stream('D4')
        self.fill_stream_with_events(s1, 420, ts, 60)
        self.fill_stream_with_events(s2, 420, ts, 60)
        self.fill_stream_with_events(s3, 300, ts + datetime.timedelta(hours=2), 60)
        self.fill_stream_with_events(s4, 240, ts, 60)

        sa1 = self.create_alias(self.u3, 'A1', self.o3, [
            {
                'ts': ts,
                'stream': s1,
            },
            {
                'ts': ts + datetime.timedelta(hours=1),
                'stream': s4,
            },
            {
                'ts': ts + datetime.timedelta(hours=2),
                'stream': s3,
            },
            {
                'ts': ts + datetime.timedelta(hours=3),
                'stream': s4,
            },
            {
                'ts': ts + datetime.timedelta(hours=4),
                'stream': s1,
            },
            {
                'ts': ts + datetime.timedelta(hours=5),
                'stream': s2,
            },
            {
                'ts': ts + datetime.timedelta(hours=6),
                'stream': s1,
            },
        ])
        sa2 = self.create_alias(self.u3, 'A2', self.o3, [
            {
                'ts': ts + datetime.timedelta(hours=3.5),
                'stream': s4,
            },
            {
                'ts': ts + datetime.timedelta(hours=4),
                'stream': s1,
            },
            {
                'ts': ts + datetime.timedelta(hours=5),
                'stream': s2,
            },
            {
                'ts': ts + datetime.timedelta(hours=6),
                'stream': s1,
            },
        ])
        sa3 = self.create_alias(self.u3, 'A3', self.o3, [
            {
                'ts': ts + datetime.timedelta(hours=1),
                'stream': s2,
            },
            {
                'ts': ts + datetime.timedelta(hours=2),
                'stream': s4,
            },
            {
                'ts': ts + datetime.timedelta(hours=4),
                'stream': s3,
            },
            {
                'ts': ts + datetime.timedelta(hours=5),
                'stream': s2,
            },
            {
                'ts': ts + datetime.timedelta(hours=6),
                'stream': s4,
            },
        ])

        response = self.client.get(url+'?staff=1&filter={}'.format(sa1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 420)
        results = deserialized['results']
        # assert results are ordered by timestamp
        self.assert_results_are_ordered_by_timestamp(results)

        self.assert_data_from_correct_stream(results, [
            {
                'start': ts,
                'end': ts + datetime.timedelta(hours=1),
                'stream': s1,
            },
            {
                'start': ts + datetime.timedelta(hours=1),
                'end': ts + datetime.timedelta(hours=2),
                'stream': s4,
            },
            {
                'start': ts + datetime.timedelta(hours=2),
                'end': ts + datetime.timedelta(hours=3),
                'stream': s3,
            },
            {
                'start': ts + datetime.timedelta(hours=3),
                'end': ts + datetime.timedelta(hours=4),
                'stream': s4,
            },
            {
                'start': ts + datetime.timedelta(hours=4),
                'end': ts + datetime.timedelta(hours=5),
                'stream': s1,
            },
            {
                'start': ts + datetime.timedelta(hours=5),
                'end': ts + datetime.timedelta(hours=6),
                'stream': s2,
            },
            {
                'start': ts + datetime.timedelta(hours=6),
                'end': ts + datetime.timedelta(hours=7),
                'stream': s1,
            },
        ])

        response = self.client.get(url+'?staff=1&filter={}'.format(sa2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 210)
        results = deserialized['results']
        # assert results are ordered by timestamp
        self.assert_results_are_ordered_by_timestamp(results)

        self.assert_data_from_correct_stream(results, [
            {
                'start': ts + datetime.timedelta(hours=3.5),
                'end': ts + datetime.timedelta(hours=4),
                'stream': s4,
            },
            {
                'start': ts + datetime.timedelta(hours=4),
                'end': ts + datetime.timedelta(hours=5),
                'stream': s1,
            },
            {
                'start': ts + datetime.timedelta(hours=5),
                'end': ts + datetime.timedelta(hours=6),
                'stream': s2,
            },
            {
                'start': ts + datetime.timedelta(hours=6),
                'end': ts + datetime.timedelta(hours=7),
                'stream': s1,
            },
        ])

        response = self.client.get(url+'?staff=1&filter={}'.format(sa3.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 300)
        results = deserialized['results']
        # assert results are ordered by timestamp
        self.assert_results_are_ordered_by_timestamp(results)

        self.assert_data_from_correct_stream(results, [
            {
                'start': ts + datetime.timedelta(hours=1),
                'end': ts + datetime.timedelta(hours=2),
                'stream': s2,
            },
            {
                'start': ts + datetime.timedelta(hours=2),
                'end': ts + datetime.timedelta(hours=4),
                'stream': s4,
            },
            {
                'start': ts + datetime.timedelta(hours=4),
                'end': ts + datetime.timedelta(hours=5),
                'stream': s3,
            },
            {
                'start': ts + datetime.timedelta(hours=5),
                'end': ts + datetime.timedelta(hours=6),
                'stream': s2,
            },
        ])

        # Test Case no.3
        ##################

        # D1: \/
        # D2:   \/
        # D3:     \/
        # ...
        # D19:                    \/
        # D20:                      \/
        #
        # A1: \/\/\/ ...  ..  ... \/\/

        streams = [self.create_device_and_associated_stream(f'D{i}') for i in range(1, 21)]
        taps = []
        slices_list = []
        for i, s in enumerate(streams):
            self.fill_stream_with_events(s, 120, ts, 10)
            taps.append({
                'ts': ts + datetime.timedelta(minutes=i),
                'stream': s,
            })
            slices_list.append({
                'start': ts + datetime.timedelta(minutes=i),
                'end': ts + datetime.timedelta(minutes=i+1),
                'stream': s
            })
        sa1 = self.create_alias(self.u3, 'A1', self.o3, taps)

        response = self.client.get(url+'?staff=1&filter={}'.format(sa1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 120)
        results = deserialized['results']
        # assert results are ordered by timestamp
        self.assert_results_are_ordered_by_timestamp(results)
        self.assert_data_from_correct_stream(results, slices_list)

        self.client.logout()

    def testVirtualStreamNoStreamId(self):
        url = reverse('streameventdata-list')

        slug = 's--{}--0000-0000-0000-0000--5555'.format(self.p2.formatted_gid)

        ts_now1 = timezone.now()
        StreamEventData.objects.create(
            timestamp=timezone.now(),
            device_timestamp=10,
            stream_slug=slug,
            streamer_local_id=100,
        )
        StreamEventData.objects.create(
            timestamp=timezone.now(),
            device_timestamp=20,
            stream_slug=slug,
            streamer_local_id=200,
        )
        StreamEventData.objects.create(
            timestamp=timezone.now(),
            device_timestamp=30,
            stream_slug=slug,
            streamer_local_id=300,
        )

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url+'?filter={}'.format(slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        self.client.logout()
