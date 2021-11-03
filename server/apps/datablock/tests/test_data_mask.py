import json
import datetime
import dateutil.parser
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from rest_framework.reverse import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from apps.utils.test_util import TestMixin
from apps.stream.models import StreamVariable, StreamId
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.streamnote.models import StreamNote
from apps.streamfilter.models import *
from apps.utils.timezone_utils import str_utc
from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.data_mask.mask_utils import *

from ..models import *

user_model = get_user_model()


class BlockDataMaskTests(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=1,
        )
        self.v2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p1, created_by=self.u3, lid=2,
        )
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p1, label='d2', template=self.dt1, created_by=self.u2)
        StreamId.objects.create_after_new_device(self.pd1)
        StreamId.objects.create_after_new_device(self.pd2)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()
        self.s2 = StreamId.objects.filter(variable=self.v2).first()

    def tearDown(self):
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        StreamNote.objects.all().delete()
        Device.objects.all().delete()
        DataBlock.objects.all().delete()
        StreamData.objects.all().delete()
        StreamEventData.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testMaskFormPost(self):

        self.assertEqual(StreamNote.objects.count(), 0)
        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)
        block = DataBlock.objects.create(org=self.o1, title='test', device=device, block=1, created_by=self.u1)
        StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=device, block=block, created_by=self.u2
        )
        StreamId.objects.create_stream(
            project=self.p1, variable=self.v2, device=device, block=block, created_by=self.u2
        )

        url = block.get_mask_url()

        # Default server time zone is UTC
        payload = {
            'start': '2018-01-02 20:31:41'
        }

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertEqual(ok, True)

        resp = self.client.post(url, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)

        self.assertEqual(StreamEventData.objects.count(), 1)
        event = StreamEventData.objects.first()

        self.assertEqual(event.extra_data['start'], '2018-01-02T20:31:00Z')
        self.assertEqual(event.extra_data['end'], None)
        self.assertEqual(StreamNote.objects.count(), 1)

        payload = {
            'start': '2018-01-02 20:31:41',
            'end': '2018-01-02 20:33:21',
        }
        resp = self.client.post(url, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)

        self.assertEqual(StreamEventData.objects.count(), 1)
        event = StreamEventData.objects.first()

        self.assertEqual(event.extra_data['start'], '2018-01-02T20:31:00Z')
        self.assertEqual(StreamNote.objects.count(), 2)

        payload = {
            'start': '2018-01-02 20:31:41',
        }
        resp = self.client.post(url, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)

        self.assertEqual(StreamEventData.objects.count(), 1)
        event = StreamEventData.objects.first()

        self.assertEqual(event.extra_data['start'], '2018-01-02T20:31:00Z')
        self.assertEqual(event.extra_data['end'], None)
        self.assertEqual(StreamNote.objects.count(), 3)


class BlockDeviceDataMaskApiTests(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=1,
        )
        self.v2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p1, created_by=self.u3, lid=2,
        )
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p1, label='d2', template=self.dt1, created_by=self.u2)
        StreamId.objects.create_after_new_device(self.pd1)
        StreamId.objects.create_after_new_device(self.pd2)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()
        self.s2 = StreamId.objects.filter(variable=self.v2).first()

    def tearDown(self):
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        StreamNote.objects.all().delete()
        Device.objects.all().delete()
        DataBlock.objects.all().delete()
        StreamData.objects.all().delete()
        StreamEventData.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testPatch(self):

        device = Device.objects.create_device(project=self.p2, org=self.p2.org,
                                              label='d1', template=self.dt1, created_by=self.u1)
        block = DataBlock.objects.create(org=self.o1, title='test', device=device, block=1, created_by=self.u1)
        stream1 = StreamId.objects.create_stream(
            project=self.p2, variable=self.v1, device=device, block=block, created_by=self.u2
        )
        stream2 = StreamId.objects.create_stream(
            project=self.p2, variable=self.v2, device=device, block=block, created_by=self.u2
        )

        url = reverse('datablock-mask', kwargs={'slug': block.slug})
        ts_now0 = parse_datetime('2018-01-02T23:31:36Z')

        for i in [10, 100, 150, 200, 270]:
            StreamData.objects.create(
                timestamp=ts_now0 + datetime.timedelta(seconds=i),
                device_timestamp=i,
                stream_slug=stream1.slug,
                type='ITR',
                streamer_local_id=i,
                value=i
            )
        for i in [11, 101, 151, 201]:
            StreamData.objects.create(
                timestamp=ts_now0 + datetime.timedelta(seconds=i),
                device_timestamp=i,
                stream_slug=stream2.slug,
                type='ITR',
                streamer_local_id=i,
                value=i
            )
            StreamEventData.objects.create(
                timestamp=ts_now0 + datetime.timedelta(seconds=i),
                device_timestamp=i,
                stream_slug=stream2.slug,
                streamer_local_id=i,
                extra_data={'value': i}
            )

        self.assertEqual(block.streamids.count(), 2)
        self.assertEqual(StreamNote.objects.filter(target_slug=block.slug).count(), 0)

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 5)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 4)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 4)

        payload = {
            'start': str_utc(ts_now0 + datetime.timedelta(seconds=101))
        }

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(self.u1.is_staff)
        self.assertTrue(block.org.has_permission(self.u1, 'can_reset_device'))

        mask_stream_slug = block.get_stream_slug_for('5a09')

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        self.assertEqual(block.streamids.count(), 2)
        self.assertEqual(StreamNote.objects.filter(target_slug=block.slug).count(), 1)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 5)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 4)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 4)
        mask_event = get_data_mask_event(block)
        self.assertEqual(mask_event.extra_data['start'], payload['start'])
        self.assertIsNone(mask_event.extra_data['end'])

        payload = {
            'start': str_utc(ts_now0 + datetime.timedelta(seconds=101)),
            'end': str_utc(ts_now0 + datetime.timedelta(seconds=201)),
        }

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        self.assertEqual(block.streamids.count(), 2)

        self.assertEqual(StreamNote.objects.filter(target_slug=block.slug).count(), 2)
        mask_event_qs = StreamEventData.objects.filter(stream_slug=mask_stream_slug)
        self.assertEqual(mask_event_qs.count(), 1)
        mask_event = mask_event_qs.first()
        self.assertEqual(mask_event.extra_data['start'], payload['start'])
        self.assertEqual(mask_event.extra_data['end'], payload['end'])

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.o1.register_user(self.u2, role='a1')
        self.assertTrue(self.o1.is_member(self.u2))
        self.assertTrue(self.o1.has_permission(self.u2, 'can_reset_device'))

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(mask_event.extra_data['start'], payload['start'])
        self.assertEqual(mask_event.extra_data['end'], payload['end'])

        self.client.logout()

    def testGet(self):

        device = Device.objects.create_device(project=self.p2, org=self.p2.org,
                                              label='d1', template=self.dt1, created_by=self.u1)
        block = DataBlock.objects.create(org=self.o1, title='test', device=device, block=1, created_by=self.u1)

        url = reverse('datablock-mask', kwargs={'slug': block.slug})

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertFalse(self.p2.org.is_member(self.u2))

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.u1.is_staff)

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertIsNone(deserialized['start'])
        self.assertIsNone(deserialized['end'])

        set_data_mask(block, '2017-01-10T10:00:00Z', None, [], [], self.u1)

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['start'], '2017-01-10T10:00:00Z')
        self.assertIsNone(deserialized['end'])

        set_data_mask(block, '2017-01-10T10:00:00Z', '2017-01-11T10:00:00Z', [], [], self.u1)

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['start'], '2017-01-10T10:00:00Z')
        self.assertEqual(deserialized['end'], '2017-01-11T10:00:00Z')

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.o1.register_user(self.u2, role='a1')
        self.assertTrue(self.o1.is_member(self.u2))
        self.assertTrue(self.o1.has_permission(self.u2, 'can_reset_device'))

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['start'], '2017-01-10T10:00:00Z')
        self.assertEqual(deserialized['end'], '2017-01-11T10:00:00Z')

        self.client.logout()

    def testDelete(self):

        device = Device.objects.create_device(project=self.p2, org=self.p2.org,
                                              label='d1', template=self.dt1, created_by=self.u1)
        block = DataBlock.objects.create(org=self.o1, title='test', device=device, block=1, created_by=self.u1)
        StreamId.objects.create_stream(
            project=self.p2, variable=self.v1, device=device, block=block, created_by=self.u2
        )
        StreamId.objects.create_stream(
            project=self.p2, variable=self.v2, device=device, block=block, created_by=self.u2
        )
        set_data_mask(block, '2017-01-10T10:00:00Z', None, [], [], self.u1)
        self.assertIsNotNone(get_data_mask_event(block))

        url = reverse('datablock-mask', kwargs={'slug': block.slug})

        self.assertEqual(block.streamids.count(), 2)
        self.assertEqual(StreamNote.objects.filter(target_slug=block.slug).count(), 1)

        resp = self.client.delete(url, data={})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.delete(url, data={})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(self.u1.is_staff)
        self.assertTrue(block.org.has_permission(self.u1, 'can_reset_device'))

        resp = self.client.delete(url, data={})
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(StreamNote.objects.filter(target_slug=block.slug).count(), 2)

        resp = self.client.delete(url, data={})
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(StreamNote.objects.filter(target_slug=block.slug).count(), 2)

        self.assertIsNone(get_data_mask_event(block))

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.o1.register_user(self.u2, role='a1')
        self.assertTrue(self.o1.is_member(self.u2))
        self.assertTrue(self.o1.has_permission(self.u2, 'can_reset_device'))

        set_data_mask(block, '2017-01-10T10:00:00Z', None, [], [], self.u1)
        self.assertIsNotNone(get_data_mask_event(block))

        resp = self.client.delete(url, data={})
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIsNone(get_data_mask_event(block))

        self.client.logout()
