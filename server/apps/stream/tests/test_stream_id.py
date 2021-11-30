import datetime
import json

import dateutil.parser

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import dateparse, timezone
from django.utils.dateparse import parse_datetime

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.physicaldevice.models import Device
from apps.projecttemplate.models import ProjectTemplate
from apps.streamdata.models import StreamData
from apps.utils.gid.convert import *
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import str_utc
from apps.vartype.models import *

from ..models import *

user_model = get_user_model()


class StreamIdDataAPITests(TestMixin, APITestCase):

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
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)
        StreamId.objects.create_after_new_device(self.pd1)
        StreamId.objects.create_after_new_device(self.pd2)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()
        self.s2 = StreamId.objects.filter(variable=self.v2).first()

    def tearDown(self):
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testGetData(self):
        """
        Ensure we can create a new Org object.
        """
        url = reverse('streamid-data', kwargs={'slug': self.s1.slug})

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
        self.assertTrue(self.s1.has_access(self.u1))
        self.assertTrue(self.pd1.project != None)

        response = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 5)

        response = self.client.get(url+'?staff=1&end=2016-09-28T11:00:00Z', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.get(url+'?staff=1&start={0}&end={1}'.format('2016-09-28T11:00:00Z', '2016-09-30T10:00:10Z'), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        response = self.client.get(url+'?staff=1&lastn=3&end={0}'.format('2016-09-30T10:00:10Z'), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url+'?staff=1&lastn=-1&end={0}'.format('2016-09-30T10:00:10Z'), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.get(url+'?staff=1&lastn=20000000000&end={0}'.format('2016-09-30T10:00:10Z'), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        self.client.logout()

    def testGetStartEndDates(self):
        """
        Ensure we can create a new Org object.
        """
        url = reverse('streamid-data', kwargs={'slug': self.s1.slug})

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

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url+'?staff=1&start=2016-09-28', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 4)

        # Date will be ignored
        response = self.client.get(url+'?staff=1&end=2016-09-28T11:00:00+00:00', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 4)

        response = self.client.get(url+'?staff=1&end={0}'.format('2016-09-28T11:00:00Z'), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

    def testMembershipAccess(self):
        url = reverse('streamid-list')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.o2.register_user(self.u3)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        self.client.logout()

    """
    def testComplexStreamValues(self):
        url = '/api/v1/stream/new_data/'
        payload = [{
            'streamid': self.s1.slug,
            'timestamp': datetime.datetime.utcnow().isoformat(),
            'type': 'Dict',
            'object_value': {
                'foo': 1,
                'bar': 4
            }
        }, {
            'streamid': self.s1.slug,
            'timestamp': datetime.datetime.utcnow().isoformat(),
            'type': 'Dict',
            'object_value': {
                'foo': 2,
                'bar': 5
            }
        }, {
            'streamid': self.s1.slug,
            'timestamp': datetime.datetime.utcnow().isoformat(),
            'type': 'Dict',
            'object_value': {
                'foo': 3,
                'bar': 6
            }
        }]

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        url = '/api/v1/stream/{0}/data/?staff=1&lastn=3'.format(str(self.s1.slug))
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)
        self.assertEqual(deserialized['results'][0]['object_value']['foo'], 1)

        self.client.logout()
    """


class StreamIdTestCase(TestMixin, TestCase):

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
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)

    def tearDown(self):
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testStreamId(self):
        self.assertEqual(formatted_gsid(pid='0001', vid='0001', did='0001'),
                         's--0000-0001--0000-0000-0000-0001--0001')
        self.assertEqual(formatted_gsid(pid='0000-0001', vid='0001', did='0000-0001'),
                         's--0000-0001--0000-0000-0000-0001--0001')
        self.assertEqual(formatted_gsid(pid='0001', vid='0001', did='0000-0000-0001'),
                         's--0000-0001--0000-0000-0000-0001--0001')
        self.assertEqual(formatted_gsid(pid='0000-0001', vid='0003', did='0000-0000-0000-0002'),
                         's--0000-0001--0000-0000-0000-0002--0003')

    def testSlug(self):
        stream = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=self.pd1, created_by=self.u2
        )
        expected = 's--{0}--{1}--{2}'.format(self.p1.formatted_gid, self.pd1.formatted_gid, self.v1.formatted_lid)
        self.assertEqual(str(stream), expected)

        stream = StreamId.objects.create_stream(
            project=self.p1, variable=None, device=self.pd1, created_by=self.u2, var_lid=2
        )
        expected = 's--{0}--{1}--{2}'.format(self.p1.formatted_gid, self.pd1.formatted_gid, '0002')
        self.assertEqual(str(stream), expected)

        stream = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=None, created_by=self.u2
        )
        expected = 's--{0}--{1}--{2}'.format(self.p1.formatted_gid, '0000-0000-0000-0000', self.v1.formatted_lid)
        self.assertEqual(str(stream), expected)

        block = DataBlock.objects.create(org=self.pd1.org, title='test', device=self.pd1, block=1, created_by=self.u2)
        stream = StreamId.objects.create_stream(
            project=None, variable=self.v1, device=self.pd1, block=block, created_by=self.u2
        )
        expected = 's--{0}--{1}--{2}'.format('0000-0000', block.formatted_gid, self.v1.formatted_lid)
        self.assertEqual(str(stream), expected)

    def testSlugChange(self):
        p10 = Project.objects.create(name='new', created_by=self.p1.created_by, org=self.p1.org)
        stream = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=self.pd1, created_by=self.u2
        )
        expected = 's--{0}--{1}--{2}'.format(self.p1.formatted_gid, self.pd1.formatted_gid, self.v1.formatted_lid)
        self.assertEqual(stream.slug, expected)
        
        # simulate device move to new project
        self.pd1.project = p10
        stream.project = p10
        stream.update_slug_from_parts()
        expected = 's--{0}--{1}--{2}'.format(p10.formatted_gid, self.pd1.formatted_gid, self.v1.formatted_lid)
        self.assertEqual(stream.slug, expected)

    def testBasicStreamIdObject(self):
        s1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=self.pd1, created_by=self.u2
        )
        expected = '{0}--{1}--{2}'.format(self.p1.formatted_gid, self.pd1.formatted_gid, self.v1.formatted_lid)
        self.assertEqual(s1.formatted_gid, expected)
        slug_expected = 's--{0}'.format(expected)
        self.assertEqual(s1.slug, slug_expected)
        self.assertEqual(str(s1), slug_expected)

        # Test that IDs stay after removing a Device
        s1.device = None
        s1.save()
        self.assertEqual(s1.formatted_gid, expected)
        self.assertEqual(s1.slug, slug_expected)
        self.assertEqual(str(s1), slug_expected)

        other_slug = s1.get_stream_slug_for('9999')
        self.assertEqual(str(other_slug), 's--{0}--{1}--9999'.format(self.p1.formatted_gid, self.pd1.formatted_gid))

    def testManagerCreate(self):
        s = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=self.pd1, created_by=self.u2
        )
        self.assertIsNotNone(s)
        self.assertEqual(s.org, self.p1.org)

        with self.assertRaises(AssertionError):
            StreamId.objects.create_stream(
                project=self.p1, variable=self.v1, device=self.pd1, created_by=self.u2, foo=1
            )

    def testHasAccess(self):
        s0 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v0, device=self.pd1, created_by=self.u2
        )
        s1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=self.pd1, created_by=self.u2
        )
        s2 = StreamId.objects.create_stream(
            project=self.p2, variable=self.v2, device=self.pd2, created_by=self.u3
        )
        self.assertTrue(s0.has_access(self.u1))
        self.assertTrue(s0.has_access(self.u2))
        self.assertFalse(s0.has_access(self.u3))
        self.assertTrue(s1.has_access(self.u1))
        self.assertTrue(s1.has_access(self.u2))
        self.assertFalse(s1.has_access(self.u3))
        self.assertTrue(s2.has_access(self.u1))
        self.assertFalse(s2.has_access(self.u2))
        self.assertTrue(s2.has_access(self.u3))
        self.assertEqual(StreamId.objects.user_streams_qs(self.u1).count(), 0)
        self.assertEqual(StreamId.objects.user_streams_qs(self.u2).count(), 2)
        self.assertEqual(StreamId.objects.user_streams_qs(self.u3).count(), 1)
        self.assertEqual(StreamId.objects.user_streams_qs(self.u2, self.p1).count(), 2)
        self.assertEqual(StreamId.objects.user_streams_qs(self.u3, self.p2).count(), 1)
        self.assertEqual(StreamId.objects.user_streams_qs(self.u2, self.p2).count(), 0)

        qs2 = StreamId.objects.user_streams_qs(self.u2)
        qs3 = StreamId.objects.user_streams_qs(self.u3)
        self.assertEqual(qs2.count(), 2)
        self.assertEqual(qs3.count(), 1)

        self.o2.register_user(self.u3)
        self.assertEqual(StreamId.objects.user_streams_qs(self.u3).count(), 3)
        self.assertEqual(StreamId.objects.user_streams_qs(self.u3, self.p1).count(), 2)

        qs3 = StreamId.objects.user_streams_qs(self.u3)
        self.assertEqual(qs3.count(), 3)

    def testAutoCreateFromVariable(self):
        self.assertEqual(StreamId.objects.count(), 0)

        StreamId.objects.create_after_new_variable(self.v1)
        self.assertEqual(StreamId.objects.count(), 1)
        self.assertEqual(self.v1.streamids.count(), 1)
        self.assertEqual(self.v2.streamids.count(), 0)

        pd3 = Device.objects.create_device(project=self.p2, label='d3', template=self.dt1, created_by=self.u3)
        StreamId.objects.create_after_new_variable(self.v2)
        self.assertEqual(StreamId.objects.count(), 3)
        self.assertEqual(pd3.streamids.count(), 1)
        self.assertEqual(self.p2.streamids.count(), 2)
        self.assertEqual(self.v1.streamids.count(), 1)
        self.assertEqual(self.v2.streamids.count(), 2)

    def testAutoCreateFromDevice(self):
        self.assertEqual(StreamId.objects.count(), 0)

        StreamId.objects.create_after_new_device(self.pd1)
        self.assertEqual(StreamId.objects.count(), 1)
        self.assertEqual(self.pd1.streamids.count(), 1)
        self.assertEqual(self.pd2.streamids.count(), 0)

        v3 = StreamVariable.objects.create_variable(
            name='Var C', project=self.p2, created_by=self.u3, lid=3,
        )
        v4 = StreamVariable.objects.create_variable(
            name='Var D', project=self.p2, created_by=self.u3, lid=4,
        )
        StreamId.objects.create_after_new_device(self.pd2)
        self.assertEqual(StreamId.objects.count(), 4)
        self.assertEqual(v3.streamids.count(), 1)
        self.assertEqual(v4.streamids.count(), 1)
        self.assertEqual(self.p2.streamids.count(), 3)
        self.assertEqual(self.v1.streamids.count(), 1)
        self.assertEqual(self.pd1.streamids.count(), 1)
        self.assertEqual(self.pd2.streamids.count(), 3)

    def testAutoCreateNoDuplicates(self):
        self.assertEqual(StreamId.objects.count(), 0)

        StreamId.objects.create_after_new_variable(self.v1)
        self.assertEqual(StreamId.objects.count(), 1)
        StreamId.objects.create_after_new_variable(self.v1)
        self.assertEqual(StreamId.objects.count(), 1)

    def testDefaultUnits(self):
        self.assertEqual(StreamId.objects.count(), 0)

        var_type = VarType.objects.create(
            name='Volume',
            storage_units_full='Liters',
            created_by=self.u1
        )
        input_unit = VarTypeInputUnit.objects.create(
            var_type=var_type,
            unit_full='Liters',
            unit_short='l',
            m=1,
            d=2,
            created_by=self.u1
        )
        output_unit = VarTypeOutputUnit.objects.create(
            var_type=var_type,
            unit_full='Gallons',
            unit_short='g',
            m=4,
            d=2,
            created_by=self.u1
        )
        va = StreamVariable.objects.create(
            name='Variable A',
            project=self.p1,
            created_by=self.u2,
            lid=100,
            input_unit=input_unit,
            output_unit=output_unit
        )

        s0 = StreamId.objects.create_stream(
            project=self.p1, variable=va, device=self.pd1, created_by=self.u2
        )
        self.assertIsNotNone(s0.input_unit)
        self.assertIsNotNone(s0.output_unit)
        self.assertEqual(s0.input_unit_id, va.input_unit_id)
        self.assertEqual(s0.output_unit_id, va.output_unit_id)
        s0.delete()

        input_unit = VarTypeInputUnit.objects.create(
            var_type=var_type,
            unit_full='Gallons',
            unit_short='g',
            m=100,
            d=20,
            created_by=self.u1
        )
        s1 = StreamId.objects.create_stream(
            project=self.p1, variable=va, device=self.pd1, created_by=self.u2, input_unit=input_unit
        )
        self.assertIsNotNone(s1.input_unit)
        self.assertIsNotNone(s1.output_unit)
        self.assertNotEqual(s1.input_unit_id, va.input_unit_id)
        self.assertEqual(s1.output_unit_id, va.output_unit_id)

    def testGetsWithStream(self):

        s1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=self.pd1, created_by=self.u2
        )
        s2 = StreamId.objects.create_stream(
            project=self.p2, variable=self.v2, device=self.pd2, created_by=self.u3
        )

        s1_table = reverse('org:project:stream:streamid-data-table', kwargs={
            'org_slug':self.o2.slug,
            'project_id': self.p1.id,
            'slug': s1.slug
        })
        s2_table = reverse('org:project:stream:streamid-data-table', kwargs={
            'org_slug':self.o2.slug,
            'project_id': self.p1.id,
            'slug': s2.slug
        })

        self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(s1_table)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTemplateUsed(resp, 'stream/streamid-data-table.html')
        self.assertNotContains(resp, 'Not Found', status_code=200)

        resp = self.client.get(s2_table)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.get(s2_table)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTemplateUsed(resp, 'stream/streamid-data-table.html')
        self.assertNotContains(resp, 'Not Found', status_code=200)

        resp = self.client.get(s1_table)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testDeleteStreamData(self):

        s1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=self.pd1, org=self.pd1.org, created_by=self.u2
        )

        dt1 = dateutil.parser.parse('2016-09-10T10:00:00Z')
        dt2 = dateutil.parser.parse('2016-09-10T11:00:00Z')
        dt3 = dateutil.parser.parse('2016-09-20T10:00:00Z')
        dt4 = dateutil.parser.parse('2016-09-23T10:00:00Z')
        dt5 = dateutil.parser.parse('2016-09-26T10:00:00Z')
        dt6 = dateutil.parser.parse('2016-09-29T10:00:00Z')

        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt1,
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt2,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt3,
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt4,
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt5,
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt6,
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt6 + datetime.timedelta(seconds=10),
            int_value=8
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt6 + datetime.timedelta(seconds=20),
            int_value=9
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt6 + datetime.timedelta(seconds=30),
            int_value=9
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt6 + datetime.timedelta(seconds=40),
            int_value=9
        )

        url_delete = reverse('org:project:stream:stream-data-delete', args=(self.p1.org.slug, self.p1.id, s1.slug))

        # payloads are in local time
        payload_reverse_date = {
            'date_from': '2016-09-10 11:00:00',
            'date_to': '2016-09-10 10:00:00',
            'delete_data': 'Submit'
        }

        # delete dt1,2
        payload_full = {
            'date_from': '2016-09-08 00:00:00',
            'date_to': '2016-09-12 00:00:00',
            'delete_data': 'Submit'
        }

        # delete from dt6
        payload_partial_1 = {
            'date_from': '2016-09-28 10:00:00',
            'date_to': '',
            'delete_data': 'Submit'
        }

        # delete up to dt4
        payload_partial_2 = {
            'date_to': '2016-09-24 10:00:00',
            'date_from': '',
            'delete_data': 'Submit'
        }

        payload_no_data = {
            'date_from': '2017-09-10 10:00:00',
            'date_to': '2017-09-11 10:00:00',
            'delete_data': 'Submit'
        }

        #  as the form parse datetime string as an aware datetime
        url_conf_base = reverse('org:project:stream:stream-data-delete-confirm', args=(self.p1.org.slug, self.p1.pk, s1.slug))
        url_conf_full = '{0}?from={1}&to={2}'.format(url_conf_base, str_utc(parse_datetime(payload_full['date_from'])),
                                                     str_utc(parse_datetime(payload_full['date_to'])))
        url_conf_1 = '{0}?from={1}&to={2}'.format(url_conf_base,
                                                  str_utc(parse_datetime(payload_partial_1['date_from'])), '')
        url_conf_2 = '{0}?from={1}&to={2}'.format(url_conf_base, '',
                                                  str_utc(parse_datetime(payload_partial_2['date_to'])))
        url_conf_no_data = '{0}?from={1}&to={2}'.format(url_conf_base, str_utc(parse_datetime(payload_no_data['date_from'])), str_utc(parse_datetime(payload_no_data['date_to'])))

        self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.get(url_delete)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.post(url_delete, payload_full)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.get(url_conf_full)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.post(url_conf_full)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(url_delete)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.post(url_delete, payload_reverse_date)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFormError(resp, 'form', None, 'The start date must be before the end date')

        resp = self.client.post(url_delete, payload_no_data)
        self.assertRedirects(resp, url_conf_no_data, status_code=302, target_status_code=302)

        # delete dt1,2
        resp = self.client.post(url_delete, payload_full)
        self.assertRedirects(resp, url_conf_full, status_code=302, target_status_code=200)

        resp = self.client.get(url_conf_full)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 10)

        resp = self.client.post(url_conf_full)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 8)

        # delete from dt6
        resp = self.client.post(url_delete, payload_partial_1)
        self.assertRedirects(resp, url_conf_1, status_code=302, target_status_code=200)

        resp = self.client.get(url_conf_1)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 8)

        resp = self.client.post(url_conf_1)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 3)

        # delete up to dt4
        resp = self.client.post(url_delete, payload_partial_2)
        self.assertRedirects(resp, url_conf_2, status_code=302, target_status_code=200)

        resp = self.client.get(url_conf_2)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 3)

        resp = self.client.post(url_conf_2)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 1)

        self.client.logout()

    def testStreamLabel(self):
        self.assertEqual(get_auto_stream_label('Very looooooooooooooooooooooooooooooong device label', 'IO2'),
                         '..ooooooooooooooooooooooooooong device label - IO2')
        device_label = 'abcdefghij' * 4
        self.assertEqual(get_auto_stream_label(device_label, 'IOIO12'),
                         '{} - IOIO12'.format(device_label))
        self.assertEqual(get_auto_stream_label('Device', 'IO2'), 'Device - IO2')

    def testProjectUiLabel(self):
        s = StreamId.objects.create_stream(
            project=self.p1, variable=self.v0, device=self.pd1, created_by=self.u2
        )
        self.assertEqual(s.data_label, '')
        self.assertEqual(s.project_ui_label, '{0} - {1}'.format(self.pd1.label, self.v0.name))
        s.data_label = 'foo name'
        self.assertEqual(s.project_ui_label, 'foo name')


class StreamIdAPITests(TestMixin, APITestCase):

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
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)

    def tearDown(self):
        StreamData.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testGetStreamWithSlug(self):
        """
        Ensure we can call GET a streamid.
        """
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        self.pd1.id = 1
        self.pd1.save()
        s = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=self.pd1, created_by=self.u2
        )
        self.assertEqual(s.slug, 's--{0}--0000-0000-0000-0001--0001'.format(self.p1.formatted_gid))

        for ok_slug in ['s--{0}--0001--0001'.format(self.p1.formatted_gid),
                        's--{0}--0000-0001--0001'.format(self.p1.formatted_gid)]:
            url = reverse('streamid-detail', kwargs={'slug': ok_slug})

            resp = self.client.get(url, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            deserialized = json.loads(resp.content.decode())
            self.assertEqual(deserialized['slug'], str(s.slug))

        for fail_slug in ['foo', '0001--0001--0001', str(s.id)]:
            url = reverse('streamid-detail', kwargs={'slug': fail_slug})

            resp = self.client.get(url, format='json')
            self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def testGetStreamWithDeviceFilter(self):
        """
        Test we can get stream ids for a given device
        """
        pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u2)
        self.assertEqual(self.p1.org, pd1.org)
        self.assertEqual(self.p2.org, pd2.org)
        StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=pd1, created_by=self.u2
        )
        StreamId.objects.create_stream(
            project=self.p1, variable=self.v2, device=pd1, created_by=self.u2
        )
        StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=pd2, created_by=self.u2
        )
        StreamId.objects.create_stream(
            project=self.p1, variable=self.v2, device=pd2, created_by=self.u2
        )

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        url = reverse('streamid-list')
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)

        url = reverse('streamid-list') + '?device__slug={0}'.format(pd1.slug)
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)
        for stream in deserialized['results']:
            self.assertEqual(stream['device'], pd1.slug)

        url = reverse('streamid-list') + '?device={0}'.format(pd1.slug)
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)
        for stream in deserialized['results']:
            self.assertEqual(stream['device'], pd1.slug)

        self.client.logout()

    def testGetWithInactiveDevices(self):
        """
        Test we can get stream ids for a given device
        """
        pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u2)
        StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=pd1, created_by=self.u2
        )
        StreamId.objects.create_stream(
            project=self.p1, variable=self.v2, device=pd1, created_by=self.u2
        )
        StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=pd2, created_by=self.u2
        )
        StreamId.objects.create_stream(
            project=self.p1, variable=self.v2, device=pd2, created_by=self.u2
        )
        self.assertEqual(StreamId.objects.count(), 4)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        url = reverse('streamid-list')
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)

        pd2.active = False
        pd2.save()
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        resp = self.client.get(url+'?all=0', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        resp = self.client.get(url+'?all=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)

        # Test that after we archive, streams are visible, even if device is inactive
        db2 = DataBlock.objects.create(org=pd1.org, title='test', device=pd2, block=1, created_by=self.u2)
        for s in pd1.streamids.filter(block__isnull=True):
            StreamId.objects.clone_into_block(s, db2)
        self.assertEqual(StreamId.objects.count(), 6)

        resp = self.client.get(url+'?device={}'.format(pd2.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        # This should work as that is how the WebApp queries for streams for an archive
        resp = self.client.get(url+'?device={}'.format(db2.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)
        for item in deserialized['results']:
            self.assertTrue(item['block'] == db2.slug)

        resp = self.client.get(url+'?archived=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)
        for item in deserialized['results']:
            self.assertTrue(item['block'] == db2.slug)

        self.client.logout()

    def testGetStreamWithProjectFilter(self):
        """
        Test we can get stream ids for a given device
        """
        pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u2)
        StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=pd1, created_by=self.u2
        )
        StreamId.objects.create_stream(
            project=self.p2, variable=self.v2, device=pd2, created_by=self.u2
        )
        self.o3.register_user(self.u2)
        self.assertTrue(self.p1.has_access(self.u2))
        self.assertTrue(self.p2.has_access(self.u2))

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        url = reverse('streamid-list')
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        url = reverse('streamid-list') + '?project={0}'.format(str(self.p1.id))
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        for stream in deserialized['results']:
            self.assertEqual(stream['project'], self.p1.slug)

        url = reverse('streamid-list') + '?project={0}'.format(self.p1.slug)
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        for stream in deserialized['results']:
            self.assertEqual(stream['project'], self.p1.slug)

        self.client.logout()

    def testPatchMdo(self):
        """
        Ensure we can modify MDO
        """

        s = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=self.pd1, created_by=self.u2
        )
        url = reverse('streamid-detail', kwargs={'slug': s.slug})

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        data = {
            'multiplication_factor':10,
            'division_factor': 20,
            'offset': 5.0,
            'mdo_label': 'Pulse/Unit'
        }

        resp = self.client.patch(url, data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        s1 = StreamId.objects.last()
        self.assertEqual(s1.multiplication_factor, 10)
        self.assertEqual(s1.division_factor, 20)
        self.assertEqual(s1.offset, 5.0)
        self.assertEqual(s1.mdo_label, 'Pulse/Unit')

        self.client.logout()

    def testPost(self):
        """
        Test that we can create a Stream off a device and variable
        """

        url = reverse('streamid-list')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        data = {
            'device': self.pd1.slug,
            'variable': self.v2.slug
        }

        count = StreamId.objects.count()

        # Variable and Device not in same project: 404
        resp = self.client.post(url, data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        data['device'] = self.pd2.slug
        resp = self.client.post(url, data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.assertEqual(StreamId.objects.count(), count + 1)
        s1 = StreamId.objects.filter(device=self.pd2, variable=self.v2).last()
        self.assertEqual(s1.project, self.v2.project)
        self.assertEqual(s1.org, self.v2.org)
        self.assertEqual(s1.var_type, self.v2.var_type)
        self.assertEqual(s1.multiplication_factor, 1)
        self.assertEqual(s1.division_factor, 1)
        self.assertEqual(s1.offset, 0.0)

        self.client.logout()

    def testStreamPostNoDevice(self):
        """
        Test that we can create a Stream off a variable without a device
        and with it, make a virtual stream
        """

        url = reverse('streamid-list')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        data = {
            'variable': self.v2.slug
        }

        count = StreamId.objects.count()

        resp = self.client.post(url, data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.assertEqual(StreamId.objects.count(), count + 1)
        s1 = StreamId.objects.filter(project=self.v2.project, variable=self.v2, device__isnull=True).last()
        self.assertEqual(s1.org, self.v2.org)
        self.assertEqual(s1.var_type, self.v2.var_type)
        self.assertEqual(s1.multiplication_factor, 1)
        self.assertEqual(s1.division_factor, 1)
        self.assertEqual(s1.offset, 0.0)

        self.client.logout()
