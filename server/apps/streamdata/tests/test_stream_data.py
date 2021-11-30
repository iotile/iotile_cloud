import csv
import datetime
import json
from io import StringIO
from unittest import mock

import dateutil.parser

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.physicaldevice.models import Device
from apps.stream.helpers import StreamDataDisplayHelper, StreamDataQueryHelper
from apps.stream.models import StreamId, StreamVariable
from apps.streamalias.models import StreamAlias, StreamAliasTap
from apps.streamfilter.models import State, StateTransition, StreamFilter, StreamFilterAction, StreamFilterTrigger
from apps.utils.data_mask.mask_utils import set_data_mask
from apps.utils.mdo.helpers import MdoHelper
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import str_utc
from apps.utils.utest.utils.alias_utils import TestStreamAliasHelper
from apps.vartype.models import VarType, VarTypeInputUnit, VarTypeOutputUnit

from ..helpers import StreamDataBuilderHelper
from ..models import *
from ..serializers import StreamDataSerializer
from ..utils import get_stream_input_mdo, get_stream_mdo, get_stream_output_mdo

user_model = get_user_model()


class StreamDataAPITests(TestMixin, TestStreamAliasHelper, APITestCase):

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
            name='Volume',
            storage_units_full='Liters',
            created_by=self.u1
        )
        self.input_unit1 = VarTypeInputUnit.objects.create(
            var_type=self.var_type,
            unit_full='Liters',
            unit_short='l',
            m=1,
            d=2,
            created_by=self.u1
        )
        self.input_unit2 = VarTypeInputUnit.objects.create(
            var_type=self.var_type,
            unit_full='Gallons',
            unit_short='g',
            m=4,
            d=2,
            created_by=self.u1
        )

        if cache:
            cache.clear()

    def tearDown(self):
        StreamFilterAction.objects.all().delete()
        StreamFilterTrigger.objects.all().delete()
        StreamFilter.objects.all().delete()
        StreamData.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testApiSerializer(self):
        payload = {}
        serializer = StreamDataSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

        payload = {
            'stream': 's--0000-0000--0123-0000-0123-0001--0001',
            'timestamp': timezone.now(),
            'int_value': 100
        }
        serializer = StreamDataSerializer(data=payload)
        self.assertTrue(serializer.is_valid())

    def testFilterUserAccess(self):
        url = reverse('streamdata-list')

        ts_now1 = timezone.now()
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=ts_now1,
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=self.s2.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=8
        )
        StreamData.objects.create(
            stream_slug=self.s2.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=9
        )
        sys_stream = '--'.join(['s', self.s2.project.formatted_gid, self.pd2.formatted_gid, '5800'])
        StreamData.objects.create(
            stream_slug=sys_stream,
            type='Num',
            timestamp=timezone.now(),
            int_value=10
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

        response = self.client.get(url+'?staff=1&filter={}'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url+'?staff=1&filter={}'.format(self.s2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        response = self.client.get(url+'?staff=1&filter={}'.format(self.pd1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url+'?staff=1&filter={}'.format(self.pd2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url+'?staff=1&filter={}'.format(sys_stream), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url+'?filter={}'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url+'?filter={}'.format(self.s2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url+'?staff=1&filter={}'.format(self.s2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url+'?filter={}'.format(self.pd1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url+'?filter={}'.format(self.pd2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url+'?staff=1&filter={}'.format(self.pd2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url+'?filter={}'.format(sys_stream), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url+'?filter={}'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url+'?filter={}'.format(self.s2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        response = self.client.get(url+'?filter={}'.format(self.pd1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url+'?filter={}'.format(self.pd2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url+'?filter={}'.format(sys_stream), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

    def testSreamAliasUserAccess(self):
        url = reverse('streamdata-list')

        ts = dateutil.parser.parse('2016-09-28T10:00:00Z')

        d0 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            device_timestamp=10,
            streamer_local_id=100,
            timestamp=ts,
            int_value=5
        )
        d1 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            device_timestamp=20,
            streamer_local_id=101,
            timestamp=ts + datetime.timedelta(seconds=10),
            int_value=6
        )
        d2 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            device_timestamp=30,
            streamer_local_id=102,
            timestamp=ts + datetime.timedelta(seconds=20),
            int_value=7
        )
        d3 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            device_timestamp=40,
            streamer_local_id=103,
            timestamp=ts + datetime.timedelta(seconds=30),
            int_value=8
        )
        d4 = StreamData.objects.create(
            stream_slug=self.s3.slug,
            type='Num',
            timestamp=ts + datetime.timedelta(seconds=20),
            int_value=8
        )
        d5 = StreamData.objects.create(
            stream_slug=self.s3.slug,
            type='Num',
            timestamp=ts + datetime.timedelta(seconds=25),
            int_value=9
        )
        d6 = StreamData.objects.create(
            stream_slug=self.s2.slug,
            type='Num',
            timestamp=ts + datetime.timedelta(seconds=25),
            int_value=9
        )

        sa1 = StreamAlias.objects.create(
            name='alias for o2',
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

    def testFutureDataFilter(self):
        url = reverse('streamdata-list') + '?filter=future&staff=1'

        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now() + datetime.timedelta(days=1),
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=self.s2.slug,
            type='Num',
            timestamp=timezone.now() + datetime.timedelta(days=1),
            int_value=8
        )
        sys_stream = '--'.join(['s', self.s2.project.formatted_gid, self.pd2.formatted_gid, '5800'])
        StreamData.objects.create(
            stream_slug=sys_stream,
            type='Num',
            timestamp=timezone.now() + datetime.timedelta(days=1),
            int_value=10
        )

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        self.client.logout()

    def testPost(self):
        url = reverse('streamdata-list')
        payload = {
            'stream': self.s1.slug,
            'type': 'Num',
            'timestamp': timezone.now(),
            'int_value': 1,
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
        self.assertTrue(self.s1.has_access(self.u1))
        self.assertTrue(self.s1.project.has_access(self.u1))
        self.assertTrue(self.s1.device.has_access(self.u1))

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamData.objects.count(), 1)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['project'], self.s1.project.slug)
        self.assertEqual(deserialized['device'], self.s1.device.slug)
        self.assertEqual(deserialized['variable'], self.s1.variable.slug)

        self.client.logout()

    def testPostMany(self):
        url = reverse('streamdata-list')
        payload = []
        for i in range(5):
            item = {
                'stream': self.s1.slug,
                'type': 'Num',
                'timestamp': timezone.now().isoformat(sep=' '),
                'int_value': i,
            }
            payload.append(item)

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        self.s1.org.register_user(self.u2)

        response = self.client.post(url, payload, format='json')
        self.assertTrue(self.s1.has_access(self.u2))
        self.assertTrue(self.s1.project.has_access(self.u2))
        self.assertTrue(self.s1.device.has_access(self.u2))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 5)
        self.assertEqual(StreamData.objects.count(), 5)

        self.client.logout()

    def testGet(self):

        url = reverse('streamdata-list')

        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=self.s2.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=8
        )
        StreamData.objects.create(
            stream_slug=self.s2.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=9
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

        response = self.client.get(url+'?staff=1&filter={}'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url+'?filter={}'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        self.client.logout()

    def testGetLastN(self):

        url = reverse('streamdata-list')

        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=5,
            streamer_local_id=5
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=6,
            streamer_local_id=6
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=7,
            streamer_local_id=7
        )
        StreamData.objects.create(
            stream_slug=self.s2.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=8,
            streamer_local_id=8
        )
        StreamData.objects.create(
            stream_slug=self.s2.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=9,
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
        self.assertEqual(deserialized['results'][0]['int_value'], 7)

        response = self.client.get(url+'?staff=1&filter={}&lastn=2'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)
        self.assertEqual(deserialized['results'][0]['int_value'], 6)
        self.assertEqual(deserialized['results'][1]['int_value'], 7)

        response = self.client.get(url+'?staff=1&filter={}&lastn=-1'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(url+'?staff=1&filter={}&lastn=20000000000'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.logout()

    def testGetWithFilter(self):
        url = reverse('streamdata-list')

        d0 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            device_timestamp=10,
            streamer_local_id=100,
            timestamp=timezone.now(),
            int_value=5
        )
        d1 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            device_timestamp=11,
            streamer_local_id=101,
            timestamp=timezone.now(),
            int_value=6
        )
        d2 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            device_timestamp=12,
            streamer_local_id=102,
            timestamp=timezone.now(),
            int_value=7
        )
        d3 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            device_timestamp=13,
            streamer_local_id=103,
            timestamp=timezone.now(),
            int_value=8
        )
        StreamData.objects.create(
            stream_slug=self.s2.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=8
        )
        StreamData.objects.create(
            stream_slug=self.s2.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=9
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

    def testGetWithStreamAlias(self):
        url = reverse('streamdata-list')

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

        d0 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            device_timestamp=10,
            streamer_local_id=100,
            timestamp=ts,
            int_value=5
        )
        d1 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            device_timestamp=20,
            streamer_local_id=101,
            timestamp=ts + datetime.timedelta(seconds=10),
            int_value=6
        )
        d2 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            device_timestamp=30,
            streamer_local_id=102,
            timestamp=ts + datetime.timedelta(seconds=20),
            int_value=7
        )
        d3 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            device_timestamp=40,
            streamer_local_id=103,
            timestamp=ts + datetime.timedelta(seconds=30),
            int_value=8
        )
        d4 = StreamData.objects.create(
            stream_slug=self.s3.slug,
            type='Num',
            timestamp=ts + datetime.timedelta(seconds=20),
            int_value=8
        )
        d5 = StreamData.objects.create(
            stream_slug=self.s3.slug,
            type='Num',
            timestamp=ts + datetime.timedelta(seconds=25),
            int_value=9
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
        self.assertEqual(results[0]['int_value'], d2.int_value)        
        self.assertEqual(results[1]['timestamp'], '2016-09-28T10:00:30Z')
        self.assertEqual(results[1]['stream'], d3.stream_slug)
        self.assertEqual(results[1]['int_value'], d3.int_value)

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
        self.assertEqual(results[0]['int_value'], d1.int_value)        
        self.assertEqual(results[1]['timestamp'], '2016-09-28T10:00:20Z')
        self.assertEqual(results[1]['stream'], d4.stream_slug)
        self.assertEqual(results[1]['int_value'], d4.int_value)
        self.assertEqual(results[2]['timestamp'], '2016-09-28T10:00:25Z')
        self.assertEqual(results[2]['stream'], d5.stream_slug)
        self.assertEqual(results[2]['int_value'], d5.int_value)        
        self.assertEqual(results[3]['timestamp'], '2016-09-28T10:00:30Z')
        self.assertEqual(results[3]['stream'], d3.stream_slug)
        self.assertEqual(results[3]['int_value'], d3.int_value)

        # Test Case no.1
        ##################

        # D1: /\/\/\/\/\/\               \/\/\/\/\
        # D2:             \/\/\/\/\|| NO DATA FROM HERE
        # D3:       NO DATA HERE ||\/\/\/|| NO DATA FROM HERE
        #
        # M1: /\/\/\/\/\/\\/\/\/\/\
        # M2:                      \/\/\/\/\/\/\/\

        s1 = self.create_device_and_associated_stream('D1')
        s2 = self.create_device_and_associated_stream('D2')
        s3 = self.create_device_and_associated_stream('D3')
        # 5 hours
        self.fill_stream_with_data(s1, 600, ts, 30)
        # 3 hours
        self.fill_stream_with_data(s2, 360, ts, 30)
        # 30 minutes
        self.fill_stream_with_data(s3, 60, ts + datetime.timedelta(hours=3), 30)

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
        # D3:   NO DATA ||\/\/\/
        # D4:       \/\/\/      \/\/\/|| NO DATA FROM HERE
        #
        # A1: \/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/
        # A2:                      /\/\/\/\/\/\/\/\/\/\/
        #
        # D1:
        # D2:       \/\/\/                  \/\/\/
        # D3:   NO DATA ||            \/\/\/
        # D4:             \/\/\/\/\/\/|| NO DATA FROM HERE
        #
        # A3:       \/\/\/\/\/\/\/\/\/\/\/\/\/\/\/
        #
        s1 = self.create_device_and_associated_stream('D1')
        s2 = self.create_device_and_associated_stream('D2')
        s3 = self.create_device_and_associated_stream('D3')
        s4 = self.create_device_and_associated_stream('D4')
        self.fill_stream_with_data(s1, 420, ts, 60)
        self.fill_stream_with_data(s2, 420, ts, 60)
        self.fill_stream_with_data(s3, 300, ts + datetime.timedelta(hours=2), 60)
        self.fill_stream_with_data(s4, 240, ts, 60)

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
            self.fill_stream_with_data(s, 120, ts, 10)
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

    def testGetWithStartEndDate(self):
        base_url = reverse('streamdata-list')
        base_url += '?staff=1&filter={}'.format(self.s1.slug)

        dt1 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        dt2 = dateutil.parser.parse('2016-09-28T11:00:00Z')
        dt3 = dateutil.parser.parse('2016-09-30T10:00:00Z')

        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=dt1,
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=dt2,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=dt3,
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=dt3 + datetime.timedelta(seconds=10),
            int_value=8
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=dt3 + datetime.timedelta(seconds=20),
            int_value=9
        )

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        url = base_url+'&start={}'.format('2016-09-28T11:00:00Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 4)

        url = base_url+'&end={}'.format('2016-09-28T11:00:00Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        # Non ISO8601 dates return HTTP 400 bad request
        url = base_url+'&end={}'.format('2016-09-28T11:00:00+00:00')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        url = base_url+'&start={0}&end={1}'.format('2016-09-28T11:00:00Z', '2016-09-30T10:00:10Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        self.client.logout()

    def testGetWithStartEndDateWithDeviceMask(self):
        base_url = reverse('streamdata-list')
        base_url += '?staff=1&filter={}'.format(self.s1.slug)

        dt1 = dateutil.parser.parse('2017-09-28T10:00:00Z')
        dt2 = dateutil.parser.parse('2017-09-28T11:00:00Z')
        dt3 = dateutil.parser.parse('2017-09-30T10:00:00Z')
        dt4 = dateutil.parser.parse('2017-09-30T10:10:00Z')
        dt5 = dateutil.parser.parse('2017-09-30T10:20:00Z')

        set_data_mask(self.pd1, '2017-09-28T10:30:00Z', '2017-09-30T10:15:00Z', [], [], self.u1)

        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=dt1,
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=dt2,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=dt3,
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=dt4,
            int_value=8
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=dt5,
            int_value=9
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

    def testPostNewScheme(self):
        self.s1.mdo_type = 'S'
        self.s1.multiplication_factor = 2
        self.s1.input_unit = self.input_unit2
        self.s1.save()
        url = reverse('streamdata-list')
        payload = {
            'stream': self.s1.slug,
            'timestamp': timezone.now(),
            'int_value': 5,
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamData.objects.count(), 1)
        stream_data = StreamData.objects.last()
        self.assertEqual(stream_data.int_value, 5)
        self.assertEqual(stream_data.value, 20.0)

        self.client.logout()

    def testPostManyNewScheme(self):
        url = reverse('streamdata-list')
        payload = []
        self.s1.mdo_type = 'S'
        self.s1.multiplication_factor = 2
        self.s1.input_unit = self.input_unit2
        self.s1.save()

        for i in range(5):
            item = {
                'stream': self.s1.slug,
                'type': 'Num',
                'timestamp': timezone.now().isoformat(sep=' '),
                'int_value': i,
            }
            payload.append(item)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        self.s1.org.register_user(self.u2)
        self.assertTrue(self.s1.has_access(self.u2))
        self.assertTrue(self.s1.project.has_access(self.u2))
        self.assertTrue(self.s1.device.has_access(self.u2))


        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 5)
        self.assertEqual(StreamData.objects.count(), 5)
        stream_data = StreamData.objects.last()
        self.assertEqual(stream_data.int_value, 4)
        self.assertEqual(stream_data.value, 16.0)

        self.client.logout()

    def testGetOne(self):

        d1 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=7
        )

        url = reverse('streamdata-detail', kwargs={'pk': d1.id})

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['id'], d1.id)
        self.assertEqual(deserialized['int_value'], 5)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testGetBadPk(self):
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        s = self.pd1.streamids.first()
        data = StreamData.objects.create(
            stream_slug=s.slug,
            type='Num',
            timestamp=t0,
            int_value=6
        )
        data.deduce_slugs_from_stream_id()
        data.save()
        # Illegal record ID
        url = reverse('streamdata-list') + '{}/'.format(data.stream_slug)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.logout()

    def testPatch(self):

        d1 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=7
        )

        url = reverse('streamdata-detail', kwargs={'pk': d1.id})
        payload = {
            'int_value': 10,
            'timestamp': timezone.now()
        }

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.patch(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['id'], d1.id)
        self.assertEqual(deserialized['int_value'], 10)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.patch(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testDateTimeFormat(self):
        url = reverse('streamdata-list')

        dt1 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        dt2 = dateutil.parser.parse('2016-09-28T20:00:00-08:00')
        dt3 = dateutil.parser.parse('2016-09-29T20:00:00+03:00')

        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=dt1,
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=dt2,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=dt3,
            int_value=7
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
            'type': 'Num',
            'timestamp': '2016-10-28T20:00:00Z',
            'int_value': 15,
        }

        response = self.client.post(url, payload, format='json')
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['timestamp'], '2016-10-28T20:00:00Z')

        """
        payload = {
            'stream': self.s1.slug,
            'type': 'Num',
            'timestamp': '2016-10-28T20:00:00-08:00',
            'int_value': 15,
        }

        response = self.client.post(url, payload, format='json')
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['timestamp'], '2016-10-29T04:00:00Z')
        """

        self.client.logout()

    def testDataFrame(self):
        base_url = reverse('api-pd')
        base_url += '?filter={}'.format(self.s1.slug)

        dt1 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        dt2 = dateutil.parser.parse('2016-09-28T11:00:00Z')
        dt3 = dateutil.parser.parse('2016-09-30T10:00:00Z')

        StreamData.objects.create(
            stream_slug=self.s1.slug,
            streamer_local_id=1,
            type='Num',
            timestamp=dt1,
            int_value=5,
            device_timestamp=100,
            value=5.0
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            streamer_local_id=2,
            type='Num',
            timestamp=dt2,
            device_timestamp=120,
            int_value=6,
            value=6.0
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            streamer_local_id=3,
            type='Num',
            timestamp=dt3,
            device_timestamp=130,
            int_value=7,
            value=7.0
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            streamer_local_id=4,
            type='Num',
            timestamp=dt3 + datetime.timedelta(seconds=20),
            device_timestamp=140,
            int_value=8,
            value=8.0
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            streamer_local_id=5,
            type='Num',
            timestamp=dt3 + datetime.timedelta(seconds=40),
            device_timestamp=150,
            int_value=9,
            value=9.0
        )
        StreamData.objects.create(
            stream_slug=self.s3.slug,
            streamer_local_id=6,
            type='Num',
            timestamp=dt3 + datetime.timedelta(seconds=60),
            device_timestamp=160,
            int_value=10,
            value=10.0
        )
        system_stream_slug='s--{}--{}--5800'.format(self.s1.project.formatted_gid, self.s1.device.formatted_gid)
        StreamData.objects.create(
            stream_slug=system_stream_slug,
            streamer_local_id=7,
            type='Num',
            timestamp=dt3 + datetime.timedelta(seconds=80),
            device_timestamp=180,
            int_value=20
        )

        # Add an output unit to multiple by 2 to test MDO processing
        self.s1.output_unit = VarTypeOutputUnit.objects.create(
            var_type=self.var_type,
            unit_full='Foo',
            unit_short='f',
            m=2,
            created_by=self.u1
        )
        self.s1.save()
        self.assertIsNotNone(get_stream_output_mdo(self.s1))

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        url = base_url+'&start={}'.format('2016-09-28T11:00:00Z')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        f = StringIO(response.content.decode('ascii'))
        reader = list(csv.reader(f))
        self.assertEqual(reader[0], ['row', 'value', 'stream_slug'])
        self.assertEqual(len(reader), 5)
        self.assertEqual(reader[1][1], '6.0')
        self.assertEqual(reader[-1][1], '9.0')

        url = base_url+'&start={}&apply_mdo=1'.format('2016-09-28T11:00:00Z')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        f = StringIO(response.content.decode('ascii'))
        reader = list(csv.reader(f))
        self.assertEqual(reader[0], ['row', 'value', 'stream_slug'])
        self.assertEqual(len(reader), 5)
        self.assertEqual(reader[1][1], '12.0')
        self.assertEqual(reader[-1][1], '18.0')

        url = base_url+'&start={}&apply_mdo=1&extended=1'.format('2016-09-28T11:00:00Z')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        f = StringIO(response.content.decode('ascii'))
        reader = list(csv.reader(f))
        self.assertEqual(len(reader[0]), 5)
        self.assertEqual(reader[0], ['row', 'value', 'stream_slug', 'device_timestamp', 'streamer_local_id'])
        self.assertEqual(len(reader), 5)
        self.assertEqual(reader[1][1], '12.0')
        self.assertEqual(reader[1][2], self.s1.slug)
        self.assertEqual(reader[1][3], '120')
        self.assertEqual(reader[1][4], '2')
        self.assertEqual(reader[-1][1], '18.0')
        self.assertEqual(reader[-1][2], self.s1.slug)
        self.assertEqual(reader[-1][3], '150')
        self.assertEqual(reader[-1][4], '5')

        url = base_url+'&end={}&apply_mdo=1'.format('2016-09-28T11:00:00Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        f = StringIO(response.content.decode('ascii'))
        reader = list(csv.reader(f))
        self.assertEqual(len(reader), 2)
        self.assertEqual(reader[-1][1], '10.0')

        url = base_url+'&start={0}&end={1}&apply_mdo=1'.format('2016-09-28T11:00:00Z', '2016-09-30T10:00:10Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        f = StringIO(response.content.decode('ascii'))
        reader = list(csv.reader(f))
        self.assertEqual(len(reader), 3)
        self.assertEqual(reader[1][1], '12.0')
        self.assertEqual(reader[-1][1], '14.0')

        url = base_url+'&pivot=1&apply_mdo=1'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        f = StringIO(response.content.decode('ascii'))
        reader = list(csv.reader(f))
        self.assertEqual(reader[0], ['row', self.s1.slug])
        self.assertEqual(len(reader), 6)
        self.assertEqual(reader[1][1], '10.0')
        self.assertEqual(reader[-1][1], '18.0')

        url = base_url+'&pivot=1&stats=1&apply_mdo=1'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        f = StringIO(response.content.decode('ascii'))
        reader = list(csv.reader(f))
        self.assertEqual(len(reader[0]), 2)
        self.assertEqual(reader[0], ['row', self.s1.slug])
        self.assertEqual(len(reader), 8)
        self.assertEqual(reader[1][0], 'count')
        self.assertEqual(reader[1][1], '5.0')
        self.assertEqual(reader[2][0], 'sum')
        self.assertEqual(reader[2][1], '70.0')
        self.assertEqual(reader[3][0], 'mean')
        self.assertEqual(reader[3][1], '14.0')
        self.assertEqual(reader[4][0], 'std')
        self.assertTrue(float(reader[4][1]) > 3.0 and float(reader[4][1]) < 4.0)
        self.assertEqual(reader[5][0], 'min')
        self.assertEqual(reader[5][1], '10.0')
        self.assertEqual(reader[6][0], 'median')
        self.assertEqual(reader[6][1], '14.0')
        self.assertEqual(reader[7][0], 'max')
        self.assertEqual(reader[7][1], '18.0')

        device_url = reverse('api-pd')
        device_url += '?filter={}'.format(self.pd1)

        url = device_url + '&pivot=1&stats=1&apply_mdo=1'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        f = StringIO(response.content.decode('ascii'))
        reader = list(csv.reader(f))
        self.assertEqual(len(reader[0]), 3)
        self.assertEqual(reader[0], ['row', self.s1.slug, self.s3.slug])
        self.assertEqual(len(reader), 8)
        self.assertEqual(reader[1][0], 'count')
        self.assertEqual(reader[1][1], '5.0')
        self.assertEqual(reader[1][2], '1.0')
        self.assertEqual(reader[2][0], 'sum')
        self.assertEqual(reader[2][1], '70.0')
        self.assertEqual(reader[2][2], '10.0')
        self.assertEqual(reader[3][0], 'mean')
        self.assertEqual(reader[3][1], '14.0')
        self.assertEqual(reader[3][2], '10.0')
        self.assertEqual(reader[4][0], 'std')
        self.assertTrue(float(reader[4][1]) > 3.0 and float(reader[4][1]) < 3.5)
        self.assertEqual(reader[4][2], '')
        self.assertEqual(reader[5][0], 'min')
        self.assertEqual(reader[5][1], '10.0')
        self.assertEqual(reader[5][2], '10.0')
        self.assertEqual(reader[6][0], 'median')
        self.assertEqual(reader[6][1], '14.0')
        self.assertEqual(reader[6][2], '10.0')
        self.assertEqual(reader[7][0], 'max')
        self.assertEqual(reader[7][1], '18.0')
        self.assertEqual(reader[7][2], '10.0')

        system_url = reverse('api-pd')
        system_url += '?filter={}'.format(system_stream_slug)

        response = self.client.get(system_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        f = StringIO(response.content.decode('ascii'))
        reader = list(csv.reader(f))
        self.assertEqual(reader[0], ['row', 'int_value', 'stream_slug'])
        self.assertEqual(len(reader), 2)
        self.assertEqual(reader[1][1], '20')

        response = self.client.get(system_url+'&extended=1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        f = StringIO(response.content.decode('ascii'))
        reader = list(csv.reader(f))
        self.assertEqual(reader[0], ['row', 'int_value', 'stream_slug', 'device_timestamp', 'streamer_local_id'])
        self.assertEqual(len(reader), 2)
        self.assertEqual(reader[1][1], '20')
        self.assertEqual(reader[1][2], system_stream_slug)
        self.assertEqual(reader[1][3], '180')
        self.assertEqual(reader[1][4], '7')

        # Test mask=1
        set_data_mask(self.pd1, '2016-09-28T11:30:00Z', None, [], [], self.u1)

        url = base_url+'&start={0}&end={1}&apply_mdo=1&mask=1'.format('2016-09-28T11:00:00Z', '2016-09-30T10:00:10Z')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        f = StringIO(response.content.decode('ascii'))
        reader = list(csv.reader(f))
        self.assertEqual(len(reader), 2)
        self.assertEqual(reader[1][1], '14.0')
        self.assertEqual(reader[-1][1], '14.0')

        self.client.logout()

    def testVirtualStreamNoStreamId(self):
        url = reverse('streamdata-list')

        slug = 's--{}--0000-0000-0000-0000--5555'.format(self.p2.formatted_gid)

        ts_now1 = timezone.now()
        StreamData.objects.create(
            stream_slug=slug,
            type='Num',
            timestamp=ts_now1,
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=7
        )

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url+'?filter={}'.format(slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        self.client.logout()

    def testStreamFilters(self):
        url = reverse('streamdata-list')
        payload = {
            'stream': self.s1.slug,
            'type': 'Num',
            'timestamp': '2016-10-28T20:00:00-08:00',
            'int_value': 15,
        }

        der_var = StreamVariable.objects.create_variable(
            name='Derived', project=self.s1.project, created_by=self.u2, lid=5,
        )
        der_stream = StreamId.objects.create_stream(
            project=self.s1.project, variable=der_var, device=self.s1.device, created_by=self.u2
        )
        f = StreamFilter.objects.create_filter_from_streamid(
            name='Filter 1', input_stream=self.s1, created_by=self.u2
        )
        state1 = State.objects.create(label="state1", filter=f, created_by=self.u2)
        state2 = State.objects.create(label="state2", filter=f, created_by=self.u2)
        StreamFilterAction.objects.create(
            type='drv', created_by=self.u2, on='entry', state=state1,
            extra_payload={'output_stream':der_stream.slug}
        )
        transition1 = StateTransition.objects.create(
            src=state1, dst=state2, filter=f, created_by=self.u2
        )
        transition2 = StateTransition.objects.create(
            src=state2, dst=state1, filter=f, created_by=self.u2
        )
        StreamFilterTrigger.objects.create(
            operator='le', created_by=self.u2, filter=f, threshold=10, transition=transition1
        )

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        self.assertEqual(StreamData.objects.count(), 0)
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamData.objects.count(), 2)
        data = StreamData.objects.filter(stream_slug=der_stream.slug).first()
        self.assertIsNotNone(data)
        self.assertEqual(data.value, 15)

        payload = [{
            'stream': self.s1.slug,
            'type': 'Num',
            'timestamp': '2016-10-28T21:00:00-08:00',
            'int_value': 1,
        }, {
            'stream': self.s1.slug,
            'type': 'Num',
            'timestamp': '2016-10-28T22:00:00-08:00',
            'int_value': 12,
        }, {
            'stream': self.s1.slug,
            'type': 'Num',
            'timestamp': '2016-10-28T23:00:00-08:00',
            'int_value': 2,
        }]

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamData.objects.count(), 6)
        self.assertEqual(StreamData.objects.filter(stream_slug=der_stream.slug).count(), 2)
        data = StreamData.objects.filter(stream_slug=der_stream.slug).last()
        self.assertIsNotNone(data)
        self.assertEqual(data.value, 12)

        self.client.logout()
