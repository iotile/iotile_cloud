import json
import datetime
import dateutil.parser
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.sqsworker.exceptions import WorkerActionHardError
from apps.utils.test_util import TestMixin
from apps.utils.gid.convert import *
from apps.stream.models import StreamVariable, StreamId
from apps.physicaldevice.models import Device
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.streamnote.models import StreamNote
from apps.devicelocation.models import DeviceLocation
from apps.streamfilter.models import *
from apps.streamer.models import *
from apps.property.models import GenericProperty
from apps.report.models import GeneratedUserReport

from ..models import *
from ..worker.device_data_reset import DeviceDataResetAction

user_model = get_user_model()


class DeviceDataResetTests(TestMixin, TestCase):

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
        GenericProperty.objects.all().delete()
        Device.objects.all().delete()
        StreamData.objects.all().delete()
        StreamEventData.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testDeviceResetActionBadArguments(self):
        with self.assertRaises(WorkerActionHardError):
            DeviceDataResetAction.schedule(args={})
        with self.assertRaises(WorkerActionHardError):
            DeviceDataResetAction.schedule(args={'foobar': 5})
        with self.assertRaises(WorkerActionHardError):
            DeviceDataResetAction.schedule(args={'device_slug': 'd--0000-0000-0000-0001', 'extra-bad-arg': 'foo'})

        self.assertTrue(DeviceDataResetAction._arguments_ok({
            'device_slug': 'd--0000-0000-0000-0001', 'user': 'slug'
        }))

        action = DeviceDataResetAction()
        self.assertIsNotNone(action)
        with self.assertRaises(WorkerActionHardError):
            action.execute(arguments={'foobar': 5})

    def testDeviceResetActionNoDataDevice(self):

        action = DeviceDataResetAction()
        self.assertIsNotNone(action)
        with self.assertRaises(WorkerActionHardError):
            action.execute({'device_slug': 'd--0000-0000-0000-0001', 'user': 'user2'})

    def testPropertyDelete(self):

        GenericProperty.objects.create_int_property(slug=self.pd1.slug,
                                                    created_by=self.u1,
                                                    name='prop1', value=4)
        GenericProperty.objects.create_str_property(slug=self.pd1.slug,
                                                    created_by=self.u1,
                                                    name='prop2', value='4')
        GenericProperty.objects.create_bool_property(slug=self.pd1.slug,
                                                     created_by=self.u1, is_system=True,
                                                     name='prop3', value=True)
        self.assertEqual(GenericProperty.objects.object_properties_qs(self.pd1).count(), 3)

        action = DeviceDataResetAction()
        action._device = self.pd1
        action._clear_properties()
        self.assertEqual(GenericProperty.objects.object_properties_qs(self.pd1).count(), 1)
        system_prop = GenericProperty.objects.object_properties_qs(self.pd1).first()
        self.assertTrue(system_prop.is_system)

    def testStreamDataDelete(self):

        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)
        stream1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=device, created_by=self.u2
        )
        stream2 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v2, device=device, created_by=self.u2
        )

        StreamData.objects.create(
            stream_slug=stream1.slug,
            type='ITR',
            timestamp=timezone.now(),
            streamer_local_id=5,
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=stream1.slug,
            type='ITR',
            timestamp=timezone.now(),
            streamer_local_id=6,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=stream2.slug,
            type='ITR',
            timestamp=timezone.now(),
            streamer_local_id=7,
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=stream1.slug,
            type='ITR',
            timestamp=timezone.now(),
            streamer_local_id=8,
            int_value=8
        )
        StreamData.objects.create(
            stream_slug=stream2.slug,
            type='ITR',
            timestamp=timezone.now(),
            streamer_local_id=9,
            int_value=9
        )

        action = DeviceDataResetAction()
        action._device = device

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 3)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 2)

        action._clear_stream_data()

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 0)

    def testStreamEventDelete(self):

        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)
        stream1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=device, created_by=self.u2
        )
        stream2 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v2, device=device, created_by=self.u2
        )

        StreamEventData.objects.create(
            timestamp=timezone.now(),
            device_timestamp=10,
            stream_slug=stream1.slug,
            streamer_local_id=2
        )
        StreamEventData.objects.create(
            timestamp=timezone.now(),
            device_timestamp=10,
            stream_slug=stream1.slug,
            streamer_local_id=3
        )
        StreamEventData.objects.create(
            timestamp=timezone.now(),
            device_timestamp=10,
            stream_slug=stream2.slug,
            streamer_local_id=4
        )

        action = DeviceDataResetAction()
        action._device = device

        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 2)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 1)

        action._clear_stream_data()

        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 0)

    def testStreamNoteDelete(self):

        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)
        stream1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=device, created_by=self.u2
        )
        StreamId.objects.create_stream(
            project=self.p1, variable=self.v2, device=device, created_by=self.u2
        )

        StreamNote.objects.create(
            target_slug=stream1.slug,
            timestamp=timezone.now(),
            created_by=self.u2,
            note='Note 1'
        )
        StreamNote.objects.create(
            target_slug=stream1.slug,
            timestamp=timezone.now(),
            created_by=self.u2,
            note='Note 2'
        )
        StreamNote.objects.create(
            target_slug=stream1.slug,
            timestamp=timezone.now(),
            created_by=self.u2,
            note='Note 3'
        )
        StreamNote.objects.create(
            target_slug=device.slug,
            timestamp=timezone.now(),
            created_by=self.u1,
            note='Note 4'
        )

        action = DeviceDataResetAction()
        action._device = device

        self.assertEqual(StreamNote.objects.filter(target_slug=stream1.slug).count(), 3)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 1)

        action._clear_notes_and_locations()

        self.assertEqual(StreamNote.objects.filter(target_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 0)

        StreamNote.objects.create(
            target_slug=device.slug,
            timestamp=timezone.now(),
            created_by=self.u1,
            note='Note 4'
        )
        action = DeviceDataResetAction()
        action._device = device
        action.execute(arguments={
            'device_slug': device.slug, 'user': self.u2.slug, 'include_notes_and_locations': False
        })
        # Keep Note plus the note the worker adds
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 2)

    def testDataBlockActionResetDeviceLocations(self):

        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)

        DeviceLocation.objects.create(
            timestamp=timezone.now(),
            target_slug=device.slug,
            lat=12.1234, lon=10.000,
            user=self.u2
        )
        DeviceLocation.objects.create(
            timestamp=timezone.now(),
            target_slug=device.slug,
            lat=12.1234, lon=11.000,
            user=self.u2
        )
        DeviceLocation.objects.create(
            timestamp=timezone.now(),
            target_slug=device.slug,
            lat=12.1234, lon=12.000,
            user=self.u2
        )

        self.assertEqual(DeviceLocation.objects.count(), 3)

        action = DeviceDataResetAction()
        action._device = device

        self.assertEqual(DeviceLocation.objects.filter(target_slug=device.slug).count(), 3)

        action._clear_notes_and_locations()

        self.assertEqual(DeviceLocation.objects.filter(target_slug=device.slug).count(), 0)

        DeviceLocation.objects.create(
            timestamp=timezone.now(),
            target_slug=device.slug,
            lat=12.1234, lon=12.000,
            user=self.u2
        )

        action = DeviceDataResetAction()
        action._device = device
        action.execute(arguments={
            'device_slug': device.slug, 'user': self.u2.slug, 'include_notes_and_locations': False
        })

        self.assertEqual(DeviceLocation.objects.filter(target_slug=device.slug).count(), 1)

    def testDataBlockActionResetReports(self):

        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)

        GeneratedUserReport.objects.create(
            org=device.org,
            label='My report 1',
            source_ref=device.slug,
            created_by=self.u2
        )
        GeneratedUserReport.objects.create(
            org=device.org,
            label='My report 2',
            source_ref=device.slug,
            created_by=self.u2
        )
        self.assertEqual(GeneratedUserReport.objects.count(), 2)

        action = DeviceDataResetAction()
        action._device = device
        action._delete_generated_reports()

        self.assertEqual(GeneratedUserReport.objects.count(), 0)

    def testDeviceResetActionTestAll(self):

        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)
        stream1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=device, created_by=self.u2
        )
        stream2 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v2, device=device, created_by=self.u2
        )
        streamer = Streamer.objects.create(device=device, index=1, created_by=self.u1 )
        StreamerReport.objects.create(streamer=streamer, actual_first_id=11, actual_last_id=20, created_by=self.u1 )

        GenericProperty.objects.create_int_property(slug=device.slug,
                                                    created_by=self.u1,
                                                    name='prop1', value=4)
        GenericProperty.objects.create_str_property(slug=device.slug,
                                                    created_by=self.u1,
                                                    name='prop2', value='4')
        GenericProperty.objects.create_bool_property(slug=device.slug,
                                                     created_by=self.u1,
                                                     name='prop3', value=True)
        StreamEventData.objects.create(
            timestamp=timezone.now(),
            device_timestamp=10,
            stream_slug=stream1.slug,
            streamer_local_id=2
        )
        StreamEventData.objects.create(
            timestamp=timezone.now(),
            device_timestamp=10,
            stream_slug=stream1.slug,
            streamer_local_id=3
        )
        StreamEventData.objects.create(
            timestamp=timezone.now(),
            device_timestamp=10,
            stream_slug=stream2.slug,
            streamer_local_id=4
        )
        StreamData.objects.create(
            stream_slug=stream1.slug,
            type='ITR',
            timestamp=timezone.now(),
            streamer_local_id=5,
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=stream1.slug,
            type='ITR',
            timestamp=timezone.now(),
            streamer_local_id=6,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=stream2.slug,
            type='ITR',
            timestamp=timezone.now(),
            streamer_local_id=7,
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=stream1.slug,
            type='ITR',
            timestamp=timezone.now(),
            streamer_local_id=8,
            int_value=8
        )
        StreamData.objects.create(
            stream_slug=stream2.slug,
            type='ITR',
            timestamp=timezone.now(),
            streamer_local_id=9,
            int_value=9
        )
        StreamNote.objects.create(
            target_slug=stream1.slug,
            timestamp=timezone.now(),
            created_by=self.u2,
            note='Note 1'
        )
        StreamNote.objects.create(
            target_slug=stream1.slug,
            timestamp=timezone.now(),
            created_by=self.u2,
            note='Note 2'
        )
        StreamNote.objects.create(
            target_slug=stream1.slug,
            timestamp=timezone.now(),
            created_by=self.u2,
            note='Note 3'
        )
        StreamNote.objects.create(
            target_slug=device.slug,
            timestamp=timezone.now(),
            created_by=self.u1,
            note='Note 4'
        )
        DeviceLocation.objects.create(
            timestamp=timezone.now(),
            target_slug=device.slug,
            lat=12.1234, lon=10.000,
            user=self.u2
        )

        GeneratedUserReport.objects.create(
            org=device.org,
            label='My report 1',
            source_ref=device.slug,
            created_by=self.u2
        )

        self.assertEqual(GenericProperty.objects.object_properties_qs(device).count(), 3)

        self.assertEqual(device.streamids.count(), 2)

        self.assertEqual(device.streamers.count(), 1)
        self.assertEqual(StreamerReport.objects.count(), 1)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 3)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 2)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 2)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 1)
        self.assertEqual(StreamNote.objects.filter(target_slug=stream1.slug).count(), 3)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 1)
        self.assertEqual(DeviceLocation.objects.filter(target_slug=device.slug).count(), 1)
        self.assertEqual(GeneratedUserReport.objects.filter(source_ref=device.slug).count(), 1)

        action = DeviceDataResetAction()
        action._device = device
        action.execute(arguments={'device_slug': device.slug, 'user': self.u2.slug})

        self.assertEqual(GenericProperty.objects.object_properties_qs(device).count(), 0)

        self.assertEqual(device.streamids.count(), 2)
        self.assertEqual(device.streamers.count(), 0)
        self.assertEqual(StreamerReport.objects.count(), 0)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 0)
        self.assertEqual(StreamNote.objects.filter(target_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 1)
        system_note = StreamNote.objects.filter(target_slug=device.slug).first()
        self.assertTrue('data was cleared' in system_note.note)
        self.assertEqual(DeviceLocation.objects.filter(target_slug=device.slug).count(), 0)
        self.assertEqual(GeneratedUserReport.objects.filter(source_ref=device.slug).count(), 0)

    def testNoFullDeviceResetActionTestAll(self):

        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)
        stream1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=device, created_by=self.u2
        )
        streamer = Streamer.objects.create(device=device, index=1, created_by=self.u1 )
        StreamerReport.objects.create(streamer=streamer, actual_first_id=11, actual_last_id=20, created_by=self.u1 )

        self.assertEqual(device.streamids.count(), 1)
        self.assertEqual(device.streamers.count(), 1)
        self.assertEqual(StreamerReport.objects.count(), 1)

        action = DeviceDataResetAction()
        action._device = device
        action.execute(arguments={'device_slug': device.slug, 'user': self.u2.slug, 'full': False})

        self.assertEqual(GenericProperty.objects.object_properties_qs(device).count(), 0)

        self.assertEqual(device.streamids.count(), 1)
        self.assertEqual(device.streamers.count(), 1)
        self.assertEqual(StreamerReport.objects.count(), 0)


