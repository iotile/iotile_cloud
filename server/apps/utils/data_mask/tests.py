from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.datablock.models import DataBlock
from apps.physicaldevice.models import Device
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.streamfilter.models import *
from apps.utils.test_util import TestMixin

from .mask_utils import *

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

    def testUtilsForDevice(self):
        self.assertEqual(StreamNote.objects.count(), 0)
        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)

        event = get_data_mask_event(device)
        self.assertIsNone(event)
        set_data_mask(device, '2017-01-10T10:00:00Z', None, [], [], self.u1)
        event = get_data_mask_event(device)
        self.assertIsNotNone(event)
        self.assertTrue('start' in event.extra_data)
        self.assertTrue('end' in event.extra_data)
        self.assertEqual(event.extra_data['start'], '2017-01-10T10:00:00Z')
        self.assertEqual(event.extra_data['end'], None)
        self.assertEqual(StreamNote.objects.count(), 1)

        set_data_mask(device, None, '2017-01-10T10:00:00Z', [], [], self.u1)
        event = get_data_mask_event(device)
        self.assertIsNotNone(event)
        self.assertTrue('start' in event.extra_data)
        self.assertTrue('end' in event.extra_data)
        self.assertEqual(event.extra_data['end'], '2017-01-10T10:00:00Z')
        self.assertEqual(event.extra_data['start'], None)
        self.assertEqual(StreamNote.objects.count(), 2)

        set_data_mask(device, '2017-01-10T10:00:00Z', '2018-01-10T10:00:00Z', [], [], self.u1)

        event = get_data_mask_event(device)
        self.assertIsNotNone(event)
        self.assertTrue('start' in event.extra_data)
        self.assertTrue('end' in event.extra_data)
        self.assertEqual(event.extra_data['start'], '2017-01-10T10:00:00Z')
        self.assertEqual(event.extra_data['end'], '2018-01-10T10:00:00Z')
        self.assertEqual(StreamNote.objects.count(), 3)

        mask_data = get_data_mask_date_range(device)
        self.assertIsNotNone(mask_data)
        self.assertTrue('start' in mask_data)
        self.assertTrue('end' in mask_data)
        self.assertEqual(mask_data['start'], '2017-01-10T10:00:00Z')
        self.assertEqual(mask_data['end'], '2018-01-10T10:00:00Z')

        mask_slug = device.get_stream_slug_for(SYSTEM_VID['DEVICE_DATA_MASK'])
        mask_data = get_data_mask_date_range_for_slug(str(mask_slug))
        self.assertEqual(mask_data['start'], '2017-01-10T10:00:00Z')
        self.assertEqual(mask_data['end'], '2018-01-10T10:00:00Z')

    def testUtilsForDataBlock(self):
        self.assertEqual(StreamNote.objects.count(), 0)
        device = Device.objects.create_device(project=self.p1, label='d3', template=self.dt1, created_by=self.u2)
        block1 = DataBlock.objects.create(org=self.o1, title='test', device=device, block=1, created_by=self.u1)
        block2 = DataBlock.objects.create(org=self.o1, title='test', device=device, block=2, created_by=self.u1)

        event = get_data_mask_event(block1)
        self.assertIsNone(event)
        set_data_mask(block1, '2017-01-10T10:00:00Z', None, [], [], self.u1)
        event = get_data_mask_event(block1)
        self.assertIsNotNone(event)
        self.assertTrue('start' in event.extra_data)
        self.assertTrue('end' in event.extra_data)
        self.assertEqual(event.extra_data['start'], '2017-01-10T10:00:00Z')
        self.assertEqual(event.extra_data['end'], None)
        self.assertEqual(StreamNote.objects.count(), 1)
        event2 = get_data_mask_event(block2)
        self.assertIsNone(event2)

        set_data_mask(block1, None, '2017-01-10T10:00:00Z', [], [], self.u1)
        event = get_data_mask_event(block1)
        self.assertIsNotNone(event)
        self.assertTrue('start' in event.extra_data)
        self.assertTrue('end' in event.extra_data)
        self.assertEqual(event.extra_data['end'], '2017-01-10T10:00:00Z')
        self.assertEqual(event.extra_data['start'], None)
        self.assertEqual(StreamNote.objects.count(), 2)
        event2 = get_data_mask_event(block2)
        self.assertIsNone(event2)

        set_data_mask(block1, '2017-01-10T10:00:00Z', '2018-01-10T10:00:00Z', [], [], self.u1)

        event = get_data_mask_event(block1)
        self.assertIsNotNone(event)
        self.assertTrue('start' in event.extra_data)
        self.assertTrue('end' in event.extra_data)
        self.assertEqual(event.extra_data['start'], '2017-01-10T10:00:00Z')
        self.assertEqual(event.extra_data['end'], '2018-01-10T10:00:00Z')
        self.assertEqual(StreamNote.objects.count(), 3)

        mask_data = get_data_mask_date_range(block1)
        self.assertIsNotNone(mask_data)
        self.assertTrue('start' in mask_data)
        self.assertTrue('end' in mask_data)
        self.assertEqual(mask_data['start'], '2017-01-10T10:00:00Z')
        self.assertEqual(mask_data['end'], '2018-01-10T10:00:00Z')

        mask_slug = block1.get_stream_slug_for(SYSTEM_VID['DEVICE_DATA_MASK'])
        mask_data = get_data_mask_date_range_for_slug(str(mask_slug))
        self.assertEqual(mask_data['start'], '2017-01-10T10:00:00Z')
        self.assertEqual(mask_data['end'], '2018-01-10T10:00:00Z')
