from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.physicaldevice.models import Device
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.helpers import StreamDataBuilderHelper
from apps.streamdata.models import StreamData
from apps.streamer.models import *
from apps.streamer.serializers import *
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import *

from ...common.test_utils import create_test_data, get_reboot_slug
from ..reprocess_one_reboot import ReProcessOneRebootV2Action

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')

class ReProcessOneRebootV2ActionTestCase(TestMixin, TestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=0x5001,
        )
        self.v2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p2, created_by=self.u3, lid=0x5002,
        )
        self.pd1 = Device.objects.create_device(id=0xa, project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(id=0xb, project=self.p2, label='d2', template=self.dt1, created_by=self.u3)
        self.user_streamer1 = Streamer.objects.create(device=self.pd1, index=0, created_by=self.u2,
                                                      selector=STREAMER_SELECTOR['USER'], process_engine_ver=2)
        Streamer.objects.create(device=self.pd2, index=0, created_by=self.u3,
                                selector=STREAMER_SELECTOR['USER'], process_engine_ver=2)
        StreamId.objects.create_after_new_device(self.pd1)
        StreamId.objects.create_after_new_device(self.pd2)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()
        self.s2 = StreamId.objects.filter(variable=self.v2).first()

    def tearDown(self):
        StreamData.objects.all().delete()
        Streamer.objects.all().delete()
        StreamerReport.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testOneReboot(self):
        action = ReProcessOneRebootV2Action()
        action._device = self.pd1

        helper = StreamDataBuilderHelper()
        reboot_slug = get_reboot_slug(self.s1.project, self.s1.device, '5c00')
        stream_payload = [
            (self.s1.slug, 100, 500), # 5
            (reboot_slug, 2, 1),
            (self.s1.slug, 10, 5),
            (self.s1.slug, 20, 6),
            (self.s1.slug, 30, 7),
            (self.s1.slug, 40, 8),
            (self.s1.slug, 50, 9), # 11
            (reboot_slug, 2, 1),
            (self.s1.slug, 10, 5),
            (self.s1.slug, 20, 6),
            (self.s1.slug, 30, 7),
            (self.s1.slug, 40, 8),
            (self.s1.slug, 50, 9),
            (reboot_slug, 2, 1),
        ]
        data_entries = create_test_data(helper, stream_payload, 5)
        self.assertEqual(len(data_entries), 14)
        StreamData.objects.bulk_create(data_entries)
        self.assertEqual(StreamData.objects.count(), 14)
        reboots = []
        for reboot in StreamData.objects.filter(stream_slug=reboot_slug).all():
            reboots.append(reboot)
        reboot = reboots[1]
        ref = reboots[2]
        ref.timestamp = parse_datetime('2016-09-28T09:55:10Z')
        ref.save()
        action.execute({
            'device_slug': self.s1.device.slug,
            'reboot_id': reboot.streamer_local_id,
            'ref_id': ref.streamer_local_id
        })

        self.assertEqual(len(action._data_entries), 6)
        self.assertEqual(action._data_entries[0].timestamp, parse_datetime('2016-09-28T09:55:10Z'))
        self.assertEqual(action._data_entries[1].timestamp, parse_datetime('2016-09-28T09:55:18Z'))
        self.assertEqual(action._data_entries[2].timestamp, parse_datetime('2016-09-28T09:55:28Z'))
        self.assertEqual(action._data_entries[3].timestamp, parse_datetime('2016-09-28T09:55:38Z'))
        self.assertEqual(action._data_entries[4].timestamp, parse_datetime('2016-09-28T09:55:48Z'))
        self.assertEqual(action._data_entries[5].timestamp, parse_datetime('2016-09-28T09:55:58Z'))

        for point in action._data_entries:
            self.assertEqual(point.status, 'cln')

        reboot = reboots[1]
        ref = StreamData.objects.get(streamer_local_id=11)
        ref.timestamp = parse_datetime('2016-09-28T08:00:00Z')
        ref.save()
        action.execute({
            'device_slug': self.s1.device.slug,
            'reboot_id': reboot.streamer_local_id,
            'ref_id': ref.streamer_local_id
        })

        self.assertEqual(len(action._data_entries), 6)
        self.assertEqual(action._data_entries[0].timestamp, parse_datetime('2016-09-28T08:00:03Z'))
        self.assertEqual(action._data_entries[1].timestamp, parse_datetime('2016-09-28T08:00:11Z'))
        self.assertEqual(action._data_entries[2].timestamp, parse_datetime('2016-09-28T08:00:21Z'))
        self.assertEqual(action._data_entries[3].timestamp, parse_datetime('2016-09-28T08:00:31Z'))
        self.assertEqual(action._data_entries[4].timestamp, parse_datetime('2016-09-28T08:00:41Z'))
        self.assertEqual(action._data_entries[5].timestamp, parse_datetime('2016-09-28T08:00:51Z'))

        action.execute({
            'device_slug': self.s1.device.slug,
            'reboot_id': reboot.streamer_local_id,
            'ref_id': ref.streamer_local_id,
            'offset': 60
        })

        self.assertEqual(len(action._data_entries), 6)
        self.assertEqual(action._data_entries[0].timestamp, parse_datetime('2016-09-28T08:01:02Z'))
        self.assertEqual(action._data_entries[1].timestamp, parse_datetime('2016-09-28T08:01:10Z'))
        self.assertEqual(action._data_entries[2].timestamp, parse_datetime('2016-09-28T08:01:20Z'))
        self.assertEqual(action._data_entries[3].timestamp, parse_datetime('2016-09-28T08:01:30Z'))
        self.assertEqual(action._data_entries[4].timestamp, parse_datetime('2016-09-28T08:01:40Z'))
        self.assertEqual(action._data_entries[5].timestamp, parse_datetime('2016-09-28T08:01:50Z'))
