import json
import datetime
import dateutil.parser
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.sqsworker.exceptions import WorkerActionHardError
from apps.physicaldevice.models import Device
from apps.utils.test_util import TestMixin
from apps.utils.gid.convert import *
from apps.stream.models import StreamVariable, StreamId
from apps.physicaldevice.models import Device
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.streamnote.models import StreamNote
from apps.devicelocation.models import DeviceLocation
from apps.streamfilter.models import *
from apps.property.models import GenericProperty
from apps.report.models import GeneratedUserReport
from apps.utils.data_mask.mask_utils import set_data_mask, get_data_mask_event

from ..models import *
from ..worker.archive_device_data import ArchiveDeviceDataAction

user_model = get_user_model()


class DataBlockCreateWorkerTests(TestMixin, TestCase):

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

    def testDataBlockActionBadArguments(self):
        with self.assertRaises(WorkerActionHardError):
            ArchiveDeviceDataAction.schedule(args={})
        with self.assertRaises(WorkerActionHardError):
            ArchiveDeviceDataAction.schedule(args={'foobar': 5})
        with self.assertRaises(WorkerActionHardError):
            ArchiveDeviceDataAction.schedule(args={'data_block_slug': 'b--0000-0000-0000-0001', 'extra-bad-arg': 'foo'})

        self.assertTrue(ArchiveDeviceDataAction._arguments_ok({'data_block_slug': 'b--0000-0000-0000-0001'}))

        action = ArchiveDeviceDataAction()
        self.assertIsNotNone(action)
        with self.assertRaises(WorkerActionHardError):
            action.execute(arguments={'foobar': 5})

    def testDataBlockActionNoDataBlock(self):

        action = ArchiveDeviceDataAction()
        self.assertIsNotNone(action)
        with self.assertRaises(WorkerActionHardError):
            action.execute({'data_block_slug': 'b--0000-0000-0000-0001'})

    def testDataBlockActionMigrateProperties(self):

        db1 = DataBlock.objects.create(org=self.o1, title='test', device=self.pd1, block=1, created_by=self.u1)

        GenericProperty.objects.create_int_property(slug=self.pd1.slug,
                                                    created_by=self.u1,
                                                    name='prop1', value=4)
        GenericProperty.objects.create_str_property(slug=self.pd1.slug,
                                                    created_by=self.u1,
                                                    name='prop2', value='4')
        GenericProperty.objects.create_bool_property(slug=self.pd1.slug,
                                                     created_by=self.u1, is_system=True,
                                                     name='@prop3', value=True)
        self.assertEqual(GenericProperty.objects.object_properties_qs(self.pd1).count(), 3)
        self.assertEqual(GenericProperty.objects.object_properties_qs(db1).count(), 0)

        action = ArchiveDeviceDataAction()
        action._block = db1
        action._device = self.pd1
        action._migrate_properties()
        self.assertEqual(GenericProperty.objects.object_properties_qs(self.pd1).count(), 1)
        self.assertEqual(GenericProperty.objects.object_properties_qs(db1).count(), 3)

    def testDataBlockActionMigrateStreams(self):

        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)
        block = DataBlock.objects.create(org=self.o1, title='test', device=device, block=1, created_by=self.u1)
        stream1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=device, created_by=self.u2
        )
        stream2 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v2, device=device, created_by=self.u2
        )
        var3 = StreamVariable.objects.create_variable(
            name='Var C', project=self.p1, created_by=self.u2, lid=3,
        )
        stream3 = StreamId.objects.create_stream(
            project=self.p1, variable=var3, device=device, created_by=self.u2
        )
        self.assertEqual(self.p1.variables.count(), 3)
        count0 = StreamId.objects.count()
        self.assertEqual(device.streamids.count(), 3)

        action = ArchiveDeviceDataAction()
        action._block = block
        action._device = device
        action._clone_streams()
        self.assertEqual(StreamId.objects.count(), count0 + 3)

    def testDataBlockActionMigrateStreamData(self):

        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)
        block = DataBlock.objects.create(org=self.o1, title='test', device=device, block=1, created_by=self.u1)
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

        action = ArchiveDeviceDataAction()
        action._block = block
        action._device = device
        action._clone_streams()

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 3)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 2)

        action._migrate_stream_data()

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 0)

        new_stream1 = block.get_stream_slug_for(self.v1.formatted_lid)
        self.assertEqual(StreamData.objects.filter(stream_slug=new_stream1).count(), 3)
        new_stream2 = block.get_stream_slug_for(self.v2.formatted_lid)
        self.assertEqual(StreamData.objects.filter(stream_slug=new_stream2).count(), 2)

        self.assertEqual(StreamData.objects.filter(stream_slug=new_stream1).first().project_slug, '')

    def testDataBlockActionMigrateStreamEvents(self):

        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)
        block = DataBlock.objects.create(org=self.o1, title='test', device=device, block=1, created_by=self.u1)
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

        action = ArchiveDeviceDataAction()
        action._block = block
        action._device = device
        action._clone_streams()

        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 2)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 1)

        action._migrate_stream_events()

        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 0)

        new_stream1 = block.get_stream_slug_for(self.v1.formatted_lid)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=new_stream1).count(), 2)
        new_stream2 = block.get_stream_slug_for(self.v2.formatted_lid)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=new_stream2).count(), 1)

    def testDataBlockActionMigrateStreamNote(self):

        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)
        block = DataBlock.objects.create(org=self.o1, title='test', device=device, block=1, created_by=self.u1)
        stream1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=device, created_by=self.u2
        )
        StreamId.objects.create_stream(
            project=self.p1, variable=self.v2, device=device, created_by=self.u2
        )

        StreamNote.objects.create(
            target_slug=device.slug,
            timestamp=timezone.now(),
            created_by=self.u2,
            note='System 1',
            type='sc'
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
            created_by=self.u1,
            note='Note 3'
        )
        StreamNote.objects.create(
            target_slug=device.slug,
            timestamp=timezone.now(),
            created_by=self.u2,
            note='Note 4'
        )
        self.assertEqual(StreamNote.objects.count(), 4)

        action = ArchiveDeviceDataAction()
        action._block = block
        action._device = device
        action._clone_streams()

        self.assertEqual(StreamNote.objects.filter(target_slug=stream1.slug).count(), 2)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 2)

        action._migrate_stream_notes()

        self.assertEqual(StreamNote.objects.filter(target_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 1)

        new_stream1 = block.get_stream_slug_for(self.v1.formatted_lid)
        self.assertEqual(StreamNote.objects.count(), 4)
        self.assertEqual(StreamNote.objects.filter(target_slug=new_stream1).count(), 2)
        self.assertEqual(StreamNote.objects.filter(target_slug=block.slug).count(), 1)

    def testDataBlockActionMigrateDeviceLocations(self):

        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)
        block = DataBlock.objects.create(org=self.o1, title='test', device=device, block=1, created_by=self.u1)

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

        action = ArchiveDeviceDataAction()
        action._block = block
        action._device = device

        self.assertEqual(DeviceLocation.objects.filter(target_slug=device.slug).count(), 3)

        action._migrate_device_locations()

        self.assertEqual(DeviceLocation.objects.filter(target_slug=device.slug).count(), 0)
        self.assertEqual(DeviceLocation.objects.filter(target_slug=block.slug).count(), 3)

    def testDataBlockActionMigrateReports(self):

        db1 = DataBlock.objects.create(org=self.pd1.org, title='test', device=self.pd1, block=1, created_by=self.u2)

        GeneratedUserReport.objects.create(
            org=self.pd1.org,
            label='My report 1',
            source_ref=self.pd1.slug,
            created_by=self.u2
        )
        GeneratedUserReport.objects.create(
            org=self.pd1.org,
            label='My report 2',
            source_ref=self.pd1.slug,
            created_by=self.u2
        )

        self.assertEqual(GeneratedUserReport.objects.filter(source_ref=self.pd1.slug).count(), 2)
        self.assertEqual(GeneratedUserReport.objects.filter(source_ref=db1.slug).count(), 0)

        action = ArchiveDeviceDataAction()
        action._block = db1
        action._device = self.pd1
        action._migrate_reports()
        self.assertEqual(GeneratedUserReport.objects.filter(source_ref=self.pd1.slug).count(), 0)
        self.assertEqual(GeneratedUserReport.objects.filter(source_ref=db1.slug).count(), 2)

    def testDataBlockActionTestAll(self):
        sg = SensorGraph.objects.create(name='SG 1',
                                        major_version=1,
                                        created_by=self.u1, org=self.o1)
        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, sg=sg, created_by=self.u2)
        block = DataBlock.objects.create(org=self.o1, title='test', device=device, block=1, created_by=self.u1)
        stream1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=device, created_by=self.u2
        )
        stream2 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v2, device=device, created_by=self.u2
        )

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

        self.assertEqual(GenericProperty.objects.object_properties_qs(device).count(), 3)
        self.assertEqual(GenericProperty.objects.object_properties_qs(block).count(), 0)

        self.assertEqual(device.streamids.count(), 2)

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 3)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 2)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 2)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 1)
        self.assertEqual(StreamNote.objects.filter(target_slug=stream1.slug).count(), 3)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 1)

        action = ArchiveDeviceDataAction()
        action._block = block
        action._device = device
        action.execute(arguments={'data_block_slug': block.slug})

        self.assertEqual(GenericProperty.objects.object_properties_qs(device).count(), 0)
        self.assertEqual(GenericProperty.objects.object_properties_qs(block).count(), 3)

        self.assertEqual(device.streamids.count(), 4)

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream2.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream2.slug).count(), 0)
        self.assertEqual(StreamNote.objects.filter(target_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 1)

        new_stream1 = block.get_stream_slug_for(self.v1.formatted_lid)
        self.assertEqual(StreamId.objects.filter(slug=new_stream1).count(), 1)
        new_stream2 = block.get_stream_slug_for(self.v2.formatted_lid)
        self.assertEqual(StreamId.objects.filter(slug=new_stream2).count(), 1)

        self.assertEqual(StreamData.objects.filter(stream_slug=new_stream1).count(), 3)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=new_stream1).count(), 2)
        self.assertEqual(StreamNote.objects.filter(target_slug=new_stream1).count(), 3)
        self.assertEqual(StreamData.objects.filter(stream_slug=new_stream2).count(), 2)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=new_stream2).count(), 1)

        block = DataBlock.objects.first()
        self.assertIsNotNone(block.completed_on)
        self.assertIsNotNone(block.sg)
        self.assertEqual(block.sg, sg)

    def testDataBlockActionTestDataMask(self):
        sg = SensorGraph.objects.create(name='SG 1',
                                        major_version=1,
                                        created_by=self.u1, org=self.o1)
        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, sg=sg, created_by=self.u2)
        block = DataBlock.objects.create(org=self.o1, title='test', device=device, block=1, created_by=self.u1)
        stream1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=device, created_by=self.u2
        )

        dt1 = dateutil.parser.parse('2017-09-28T10:00:00Z')
        dt2 = dateutil.parser.parse('2017-09-28T11:00:00Z')
        dt3 = dateutil.parser.parse('2017-09-30T10:00:00Z')
        dt4 = dateutil.parser.parse('2017-09-30T10:10:00Z')
        dt5 = dateutil.parser.parse('2017-09-30T10:20:00Z')

        set_data_mask(device, '2017-09-28T10:30:00Z', '2017-09-30T10:15:00Z', [], [], self.u1)

        StreamData.objects.create(
            stream_slug=stream1.slug,
            type='Num',
            timestamp=dt1,
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=stream1.slug,
            type='Num',
            timestamp=dt2,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=stream1.slug,
            type='Num',
            timestamp=dt3,
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=stream1.slug,
            type='Num',
            timestamp=dt4,
            int_value=8
        )
        StreamData.objects.create(
            stream_slug=stream1.slug,
            type='Num',
            timestamp=dt5,
            int_value=9
        )

        self.assertEqual(device.streamids.count(), 1)

        data_mask_event = get_data_mask_event(device)
        mask_slug = data_mask_event.stream_slug
        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 5)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=mask_slug).count(), 1)

        action = ArchiveDeviceDataAction()
        action._block = block
        action._device = device
        action.execute(arguments={'data_block_slug': block.slug})

        self.assertEqual(device.streamids.count(), 2)

        self.assertEqual(StreamData.objects.filter(stream_slug=stream1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=mask_slug).count(), 0)

        data_mask_event = get_data_mask_event(block)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=data_mask_event.stream_slug).count(), 1)

