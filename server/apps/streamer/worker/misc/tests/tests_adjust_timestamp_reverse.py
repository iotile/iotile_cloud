from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.helpers import StreamDataBuilderHelper
from apps.streamdata.models import StreamData
from apps.streamer.serializers import *
from apps.streamevent.helpers import StreamEventDataBuilderHelper
from apps.streamevent.models import StreamEventData
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import *

from ...common.test_utils import create_test_data, get_reboot_slug
from ..adjust_timestamp_reverse import AdjustTimestampReverseV2Action

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')

class AdjustTimestampReverseActionTestCase(TestMixin, TestCase):

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
        StreamEventData.objects.all().delete()
        StreamData.objects.all().delete()
        Streamer.objects.all().delete()
        StreamerReport.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testDataAdjustment(self):
        action = AdjustTimestampReverseV2Action()
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
        data_entries[-1].timestamp = parse_datetime('2018-09-28T10:00:00Z')
        self.assertEqual(len(data_entries), 14)
        StreamData.objects.bulk_create(data_entries)
        self.assertEqual(StreamData.objects.count(), 14)
        action.execute({
            'device_slug': self.s1.device.slug,
            'start': 5,
            'end': 18,
            'type': 'data'
        })

        self.assertEqual(len(action._data_entries), 14)
        self.assertEqual(len(action._event_entries), 0)
        qs = StreamData.objects.filter(device_slug=self.s1.device.slug)
        self.assertEqual(qs[0].timestamp, parse_datetime('2018-09-28T09:58:18Z'))
        self.assertEqual(qs[1].timestamp, parse_datetime('2018-09-28T09:58:20Z'))
        self.assertEqual(qs[2].timestamp, parse_datetime('2018-09-28T09:58:28Z'))
        self.assertEqual(qs[3].timestamp, parse_datetime('2018-09-28T09:58:38Z'))
        self.assertEqual(qs[4].timestamp, parse_datetime('2018-09-28T09:58:48Z'))
        self.assertEqual(qs[5].timestamp, parse_datetime('2018-09-28T09:58:58Z'))
        self.assertEqual(qs[6].timestamp, parse_datetime('2018-09-28T09:59:08Z'))
        self.assertEqual(qs[7].timestamp, parse_datetime('2018-09-28T09:59:10Z'))
        self.assertEqual(qs[8].timestamp, parse_datetime('2018-09-28T09:59:18Z'))
        self.assertEqual(qs[9].timestamp, parse_datetime('2018-09-28T09:59:28Z'))
        self.assertEqual(qs[10].timestamp, parse_datetime('2018-09-28T09:59:38Z'))
        self.assertEqual(qs[11].timestamp, parse_datetime('2018-09-28T09:59:48Z'))

        last = qs.last()
        self.assertEqual(last.timestamp, parse_datetime('2018-09-28T10:00:00Z'))

        for point in qs:
            if point != last:
                self.assertEqual(point.status, 'cln', msg='failure on {}'.format(point.streamer_local_id))
