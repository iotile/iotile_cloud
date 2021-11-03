import json
import datetime
import dateutil.parser
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.sqsworker.exceptions import WorkerActionHardError
from apps.utils.test_util import TestMixin
from apps.stream.models import StreamVariable, StreamId
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.streamnote.models import StreamNote
from apps.streamfilter.models import *
from apps.utils.timezone_utils import str_utc
from apps.utils.iotile.variable import SYSTEM_VID

from ..models import *
from ..worker.device_data_trim import DeviceDataTrimAction

user_model = get_user_model()


class DeviceDataTrimTests(TestMixin, TestCase):

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
        StreamFilterAction.objects.all().delete()
        StreamFilterTrigger.objects.all().delete()
        StreamFilter.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        StreamNote.objects.all().delete()
        Device.objects.all().delete()
        StreamData.objects.all().delete()
        StreamEventData.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testDeviceResetActionBadArguments(self):
        with self.assertRaises(WorkerActionHardError):
            DeviceDataTrimAction.schedule(args={})
        with self.assertRaises(WorkerActionHardError):
            DeviceDataTrimAction.schedule(args={'foobar': 5})
        with self.assertRaises(WorkerActionHardError):
            DeviceDataTrimAction.schedule(args={
                'device_slug': 'd--0000-0000-0000-0001', 'username': 'bar', 'extra-bad-arg': 'foo'
            })

        self.assertTrue(DeviceDataTrimAction._arguments_ok({
            'device_slug': 'd--0000-0000-0000-0001', 'username': 'user1', 'start': timezone.now().isoformat()
        }))

        action = DeviceDataTrimAction()
        self.assertIsNotNone(action)
        with self.assertRaises(WorkerActionHardError):
            action.execute(arguments={'foobar': 5})

    def testDeviceTrimActionNoDataDevice(self):

        action = DeviceDataTrimAction()
        self.assertIsNotNone(action)
        with self.assertRaises(WorkerActionHardError):
            action.execute({
                'device_slug': 'd--0000-0000-0000-0001', 'username': 'user1', 'start': timezone.now().isoformat()
            })

    def testDeviceTrimActionTestAll(self):

        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)
        stream1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=device, created_by=self.u2
        )
        stream2 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v2, device=device, created_by=self.u2
        )

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

        self.assertEqual(device.streamids.count(), 2)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 0)

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 5)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 4)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 4)

        action = DeviceDataTrimAction()
        action.execute(arguments={
            'device_slug': device.slug,
            'username': self.u2.username,
            'start': str_utc(ts_now0 + datetime.timedelta(seconds=101))
        })

        self.assertEqual(device.streamids.count(), 2)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 1)

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 3)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 3)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 3)

        action.execute(arguments={
            'device_slug': device.slug,
            'username': self.u2.username,
            'start': str_utc(ts_now0 + datetime.timedelta(seconds=101)),
            'end': str_utc(ts_now0 + datetime.timedelta(seconds=201)),
        })

        self.assertEqual(device.streamids.count(), 2)

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 2)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 3)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 3)

        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 2)

    def testDeviceTrimExclusions(self):

        trip_start_var = StreamVariable.objects.create_variable(
            name='Trip Start', project=self.p1, created_by=self.u3, lid=int(SYSTEM_VID['TRIP_START'], 16),
        )
        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)
        stream1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=device, created_by=self.u2
        )
        stream2 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v2, device=device, created_by=self.u2
        )
        trip_start_stream = StreamId.objects.create_stream(
            project=self.p1, variable=trip_start_var, device=device, created_by=self.u2
        )

        ts_now0 = parse_datetime('2018-01-02T23:31:36Z')

        StreamData.objects.create(
            timestamp=ts_now0 + datetime.timedelta(seconds=5),
            device_timestamp=5,
            stream_slug=trip_start_stream.slug,
            type='ITR',
            streamer_local_id=1,
            value=1
        )

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

        self.assertEqual(device.streamids.count(), 3)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 0)

        self.assertEqual(StreamData.objects.filter(stream_slug=trip_start_stream.slug).count(), 1)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 5)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 4)

        action = DeviceDataTrimAction()
        action.execute(arguments={
            'device_slug': device.slug,
            'username': self.u2.username,
            'start': str_utc(ts_now0 + datetime.timedelta(seconds=101))
        })

        self.assertEqual(device.streamids.count(), 3)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 1)

        self.assertEqual(StreamData.objects.filter(stream_slug=trip_start_stream.slug).count(), 1)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 3)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 3)

    def testTrimFormPost(self):

        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)
        stream1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=device, created_by=self.u2
        )
        stream2 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v2, device=device, created_by=self.u2
        )

        ts_now0 = parse_datetime('2018-01-02T20:30:00Z')
        url = device.get_trim_url()
        confirm_url = reverse('org:project:device:trim-confirm', args=(device.org.slug, str(device.project.id), device.id,))

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

        self.assertEqual(device.streamids.count(), 2)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 0)

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 5)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 4)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 4)

        # Default server time zone is UTC
        payload = {
            'start': '2018-01-02 20:31:00'
        }

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertEqual(ok, True)

        resp = self.client.post(url, payload, format='json')
        redirect_url = confirm_url + '?start={}'.format('2018-01-02T20:31:00Z')
        self.assertRedirects(resp, redirect_url, status_code=302, target_status_code=200,
                             msg_prefix='', fetch_redirect_response=True)

        self.assertEqual(device.streamids.count(), 2)

        resp = self.client.post(redirect_url, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)

        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 1)

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 4)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 3)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 3)

        payload = {
            'start': '2018-01-02 20:31:00',
            'end': '2018-01-02 20:33:00'
        }
        resp = self.client.post(url, payload, format='json')
        redirect_url = confirm_url + '?start={}&end={}'.format('2018-01-02T20:31:00Z', '2018-01-02T20:33:00Z')
        self.assertRedirects(resp, redirect_url, status_code=302, target_status_code=200,
                             msg_prefix='', fetch_redirect_response=True)

        self.assertEqual(device.streamids.count(), 2)

        resp = self.client.post(redirect_url, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 2)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 2)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 2)

        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 2)

    def testTrimFormOnlyEventPost(self):

        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)
        stream1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=device, created_by=self.u2
        )
        stream2 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v2, device=device, created_by=self.u2
        )

        ts_now0 = parse_datetime('2018-01-02T20:30:00Z')
        url = device.get_trim_url()
        confirm_url = reverse('org:project:device:trim-confirm', args=(device.org.slug, str(device.project.id), device.id,))

        for i in [11, 101, 151, 201]:
            StreamEventData.objects.create(
                timestamp=ts_now0 + datetime.timedelta(seconds=i),
                device_timestamp=i,
                stream_slug=stream2.slug,
                streamer_local_id=i,
                extra_data={'value': i}
            )

        self.assertEqual(device.streamids.count(), 2)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 0)

        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 4)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertEqual(ok, True)

        payload = {
            'start': '2018-01-02 20:31:00',
            'end': '2018-01-02 20:33:00'
        }
        resp = self.client.post(url, payload, format='json')
        redirect_url = confirm_url + '?start={}&end={}'.format('2018-01-02T20:31:00Z', '2018-01-02T20:33:00Z')
        self.assertRedirects(resp, redirect_url, status_code=302, target_status_code=200,
                             msg_prefix='', fetch_redirect_response=True)

        self.assertEqual(device.streamids.count(), 2)

        resp = self.client.post(redirect_url, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)

        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 2)

        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 1)


class DeviceDataTrimApiTests(TestMixin, APITestCase):

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
        StreamFilterAction.objects.all().delete()
        StreamFilterTrigger.objects.all().delete()
        StreamFilter.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        StreamNote.objects.all().delete()
        Device.objects.all().delete()
        StreamData.objects.all().delete()
        StreamEventData.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testPost(self):

        device = Device.objects.create_device(project=self.p2, org=self.p2.org,
                                              label='d1', template=self.dt1, created_by=self.u1)
        stream1 = StreamId.objects.create_stream(
            project=self.p2, variable=self.v1, device=device, created_by=self.u2
        )
        stream2 = StreamId.objects.create_stream(
            project=self.p2, variable=self.v2, device=device, created_by=self.u2
        )

        url = reverse('device-trim', kwargs={'slug': device.slug})
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

        self.assertEqual(device.streamids.count(), 2)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 0)

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 5)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 4)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 4)

        payload = {
            'start': str_utc(ts_now0 + datetime.timedelta(seconds=101))
        }

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(self.u1.is_staff)
        self.assertTrue(device.org.has_permission(self.u1, 'can_modify_device'))

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        self.assertEqual(device.streamids.count(), 2)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 1)

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 3)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 3)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 3)

        payload = {
            'start': str_utc(ts_now0 + datetime.timedelta(seconds=101)),
            'end': str_utc(ts_now0 + datetime.timedelta(seconds=201)),
        }

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        self.assertEqual(device.streamids.count(), 2)

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 2)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 3)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 3)

        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 2)

        self.client.logout()

