import datetime
import json

import dateutil.parser

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.devicelocation.models import DeviceLocation
from apps.physicaldevice.models import Device
from apps.property.models import GenericProperty
from apps.report.models import GeneratedUserReport
from apps.sqsworker.exceptions import WorkerActionHardError
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.streamfilter.models import *
from apps.streamnote.models import StreamNote
from apps.utils.data_mask.mask_utils import get_data_mask_event, set_data_mask
from apps.utils.test_util import TestMixin

from ..models import *
from ..worker.archive_device_data import ArchiveDeviceDataAction
from ..worker.datablock_delete import DataBlockDeleteAction

user_model = get_user_model()


class DataBlockDeleteWorkerTests(TestMixin, TestCase):

    def _create_archive(self):
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
            target_slug=device.slug,
            timestamp=timezone.now(),
            created_by=self.u1,
            note='Note 3'
        )
        DeviceLocation.objects.create(
            timestamp=timezone.now(),
            target_slug=device.slug,
            user=self.u2
        )

        action = ArchiveDeviceDataAction()
        action._block = block
        action._device = self.pd1
        action.execute(arguments={'data_block_slug': block.slug})

        return block

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

        StreamData.objects.create(
            stream_slug=self.s2.slug,
            type='ITR',
            timestamp=timezone.now(),
            streamer_local_id=9,
            int_value=9
        )
        StreamNote.objects.create(
            target_slug=self.pd2.slug,
            timestamp=timezone.now(),
            created_by=self.u2,
            note='Note 1'
        )
        DeviceLocation.objects.create(
            timestamp=timezone.now(),
            target_slug=self.pd2.slug,
            user=self.u2
        )

    def tearDown(self):
        StreamFilterAction.objects.all().delete()
        StreamFilterTrigger.objects.all().delete()
        StreamFilter.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        GenericProperty.objects.all().delete()
        Device.objects.all().delete()
        StreamNote.objects.all().delete()
        StreamData.objects.all().delete()
        StreamEventData.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testDataBlockActionBadArguments(self):
        with self.assertRaises(WorkerActionHardError):
            DataBlockDeleteAction.schedule(args={})
        with self.assertRaises(WorkerActionHardError):
            DataBlockDeleteAction.schedule(args={'foobar': 5})
        with self.assertRaises(WorkerActionHardError):
            DataBlockDeleteAction.schedule(args={'block_slug': 'b--0000-0000-0000-0001', 'extra-bad-arg': 'foo'})

        self.assertTrue(DataBlockDeleteAction._arguments_ok({
            'block_slug': 'b--0000-0000-0000-0001',
            'user': 'user1'
        }))

        action = DataBlockDeleteAction()
        self.assertIsNotNone(action)
        with self.assertRaises(WorkerActionHardError):
            action.execute(arguments={'foobar': 5})

    def testDataBlockActionNoDataBlock(self):

        action = DataBlockDeleteAction()
        self.assertIsNotNone(action)
        with self.assertRaises(WorkerActionHardError):
            action.execute({'block_slug': 'b--0000-0000-0000-0001', 'user': 'user1'})

    def testDataBlockActionMDeleteProperties(self):

        block = self._create_archive()

        self.assertEqual(GenericProperty.objects.object_properties_qs(block).count(), 3)
        self.assertEqual(StreamId.objects.count(), 8)
        self.assertEqual(block.streamids.count(), 2)
        self.assertEqual(StreamData.objects.count(), 4)
        self.assertEqual(StreamEventData.objects.count(), 2)
        self.assertEqual(StreamNote.objects.count(), 5)
        self.assertEqual(DeviceLocation.objects.count(), 2)

        action = DataBlockDeleteAction()
        action.execute(arguments={'block_slug': block.slug, 'user': self.u2.slug})

        self.assertEqual(GenericProperty.objects.count(), 0)
        self.assertEqual(StreamId.objects.count(), 6)
        self.assertEqual(StreamData.objects.count(), 1)
        self.assertEqual(StreamEventData.objects.count(), 0)
        self.assertEqual(StreamNote.objects.count(), 2)
        system_note = StreamNote.objects.last()
        self.assertTrue('data was archived' in system_note.note)
        self.assertEqual(DeviceLocation.objects.count(), 1)

    def testDataBlockActionDeleteReports(self):

        block = self._create_archive()

        GeneratedUserReport.objects.create(
            org=block.org,
            label='My report 1',
            source_ref=block.slug,
            created_by=self.u2
        )
        GeneratedUserReport.objects.create(
            org=block.org,
            label='My report 2',
            source_ref=block.slug,
            created_by=self.u2
        )
        self.assertEqual(GeneratedUserReport.objects.count(), 2)

        action = DataBlockDeleteAction()
        action.execute(arguments={'block_slug': block.slug, 'user': self.u2.slug})

        self.assertEqual(GeneratedUserReport.objects.count(), 0)

    def testDataBlockActionDeleteDataMask(self):
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

        action = ArchiveDeviceDataAction()
        action._block = block
        action._device = device
        action.execute(arguments={'data_block_slug': block.slug})

        self.assertEqual(device.streamids.count(), 2)

        data_mask_event = get_data_mask_event(block)
        self.assertIsNotNone(data_mask_event)
        mask_slug = data_mask_event.stream_slug
        self.assertEqual(StreamEventData.objects.filter(stream_slug=mask_slug).count(), 1)

        action = DataBlockDeleteAction()
        action.execute(arguments={'block_slug': block.slug, 'user': self.u2.slug})

        self.assertEqual(StreamEventData.objects.filter(stream_slug=mask_slug).count(), 0)

