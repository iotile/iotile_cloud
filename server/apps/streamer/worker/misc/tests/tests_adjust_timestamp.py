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
from ..adjust_timestamp import AdjustTimestampAction

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')

class AdjustTimestampActionTestCase(TestMixin, TestCase):

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
        action = AdjustTimestampAction()
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
        action.execute({
            'device_slug': self.s1.device.slug,
            'start': 8,
            'end': 11,
            'base_ts': '2018-01-20T01:00:00Z',
            'type': 'data'
        })

        self.assertEqual(len(action._data_entries), 4)
        self.assertEqual(len(action._event_entries), 0)
        self.assertEqual(action._data_entries[0].timestamp, parse_datetime('2018-01-20T01:00:20Z'))
        self.assertEqual(action._data_entries[1].timestamp, parse_datetime('2018-01-20T01:00:30Z'))
        self.assertEqual(action._data_entries[2].timestamp, parse_datetime('2018-01-20T01:00:40Z'))
        self.assertEqual(action._data_entries[3].timestamp, parse_datetime('2018-01-20T01:00:50Z'))

        for point in action._data_entries:
            self.assertEqual(point.status, 'cln')

        # Test fix across reboots
        action.execute({
            'device_slug': self.s1.device.slug,
            'start': 6,
            'end': 17,
            'base_ts': '2018-02-20T01:00:00Z',
            'type': 'data'
        })

        self.assertEqual(len(action._data_entries), 12)
        self.assertEqual(len(action._event_entries), 0)
        self.assertEqual(action._data_entries[0].timestamp, parse_datetime('2018-02-20T01:00:02Z'))
        self.assertEqual(action._data_entries[1].timestamp, parse_datetime('2018-02-20T01:00:10Z'))
        self.assertEqual(action._data_entries[2].timestamp, parse_datetime('2018-02-20T01:00:20Z'))
        self.assertEqual(action._data_entries[3].timestamp, parse_datetime('2018-02-20T01:00:30Z'))
        self.assertEqual(action._data_entries[4].timestamp, parse_datetime('2018-02-20T01:00:40Z'))
        self.assertEqual(action._data_entries[5].timestamp, parse_datetime('2018-02-20T01:00:50Z'))
        self.assertEqual(action._data_entries[6].timestamp, parse_datetime('2018-02-20T01:00:52Z'))
        self.assertEqual(action._data_entries[7].timestamp, parse_datetime('2018-02-20T01:01:00Z'))
        self.assertEqual(action._data_entries[8].timestamp, parse_datetime('2018-02-20T01:01:10Z'))
        self.assertEqual(action._data_entries[9].timestamp, parse_datetime('2018-02-20T01:01:20Z'))
        self.assertEqual(action._data_entries[10].timestamp, parse_datetime('2018-02-20T01:01:30Z'))

        for point in action._data_entries:
            self.assertEqual(point.status, 'cln')


    def testEventAdjustment(self):
        action = AdjustTimestampAction()
        action._device = self.pd1

        event_helper = StreamEventDataBuilderHelper()
        event_entries = []
        event_entries.append(event_helper.process_serializer_data({
            "stream_slug": self.s1.slug,
            "device_timestamp": 100,
            "timestamp": "2018-01-20T00:00:00Z",
            "streamer_local_id": 2,
            "extra_data": {}
        }))
        event_entries.append(event_helper.process_serializer_data({
            "stream_slug": self.s1.slug,
            "device_timestamp": 160,
            "timestamp": "2018-01-20T01:12:00Z",
            "streamer_local_id": 3,
            "extra_data": {}
        }))
        event_entries.append(event_helper.process_serializer_data({
            "stream_slug": self.s1.slug,
            "device_timestamp": 220,
            "timestamp": "2018-01-20T01:12:00Z",
            "streamer_local_id": 4,
            "extra_data": {}
        }))
        event_entries.append(event_helper.process_serializer_data({
            "stream_slug": self.s1.slug,
            "device_timestamp": 280,
            "timestamp": "2018-01-20T01:12:00Z",
            "streamer_local_id": 5,
            "extra_data": {}
        }))

        StreamEventData.objects.bulk_create(event_entries)
        self.assertEqual(StreamEventData.objects.count(), 4)

        action.execute({
            'device_slug': self.pd1.slug,
            'start': 3,
            'end': 4,
            'base_ts': '2018-01-20T00:00:00Z',
            'type': 'event'
        })

        self.assertEqual(len(action._data_entries), 0)
        self.assertEqual(len(action._event_entries), 2)
        self.assertEqual(action._event_entries[0].timestamp, parse_datetime('2018-01-20T00:02:40Z'))
        self.assertEqual(action._event_entries[1].timestamp, parse_datetime('2018-01-20T00:03:40Z'))

        for point in action._event_entries:
            self.assertEqual(point.status, 'cln')
