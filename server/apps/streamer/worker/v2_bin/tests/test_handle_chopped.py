import json
import os
import time
import dateutil.parser
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils.dateparse import parse_datetime


from apps.utils.test_util import TestMixin
from apps.stream.models import StreamVariable, StreamId
from apps.streamdata.models import StreamData
from apps.streamdata.helpers import StreamDataBuilderHelper
from apps.physicaldevice.models import Device
from apps.utils.timezone_utils import *
from unittest import skipIf, mock
from apps.streamer.models import *
from apps.streamer.serializers import *

from ..handle_chopped_report import HandleChoppedReportV2Action

from ...common.test_utils import create_test_data, get_reboot_slug

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')

class StreamerV2HandleReportTestCase(TestMixin, TestCase):

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

    def testTwoReboot(self):
        action = HandleChoppedReportV2Action()
        action._received_dt = parse_datetime('2016-09-28T10:00:00Z')
        action._streamer = self.user_streamer1
        action._device = self.pd1
        action._streamer_report = StreamerReport.objects.create(streamer=self.user_streamer1,
                                                                original_first_id=4,
                                                                original_last_id=10,
                                                                actual_first_id=4,
                                                                actual_last_id=10,
                                                                device_sent_timestamp=240,
                                                                sent_timestamp=action._received_dt,
                                                                incremental_id=11,
                                                                created_by=self.u1 )

        helper = StreamDataBuilderHelper()
        reboot_slug = get_reboot_slug(self.s1.project, self.s1.device, '5c00')
        stream_payload = [
            (reboot_slug, 2, 1),
            (self.s1.slug, 10, 5),
            (self.s1.slug, 20, 6),
            (self.s1.slug, 30, 7),
            (self.s1.slug, 40, 8),
            (self.s1.slug, 50, 9),
            (self.s1.slug, 10, 20),
            (reboot_slug, 2, 1),
            (self.s1.slug, 20, 22),
            (self.s1.slug, 30, 25),
            (self.s1.slug, 40, 26),
            (self.s1.slug, 50, 27),
        ]
        entries = create_test_data(helper, stream_payload, 5)
        StreamData.objects.bulk_create(entries)
        self.assertEqual(StreamData.objects.count(), 12)

        reboot = StreamData.objects.filter(stream_slug=reboot_slug).last()
        reboot.timestamp = parse_datetime('2016-09-28T10:01:00Z')
        reboot.save()

        action._actual_first_id = 5
        action._actual_last_id = 10
        time0 = time.time()
        action.process()
        exec_time1 = time.time() - time0
        self.assertEqual(len(action._data_entries), 6)

        # base_ts for this block is 2016-09-28T09:53:00Z which is sent time from first report - 60sec
        self.assertEqual(action._data_entries[0].timestamp, parse_datetime('2016-09-28T10:00:12Z'))
        self.assertEqual(action._data_entries[1].timestamp, parse_datetime('2016-09-28T10:00:20Z'))
        self.assertEqual(action._data_entries[2].timestamp, parse_datetime('2016-09-28T10:00:30Z'))
        self.assertEqual(action._data_entries[3].timestamp, parse_datetime('2016-09-28T10:00:40Z'))
        self.assertEqual(action._data_entries[4].timestamp, parse_datetime('2016-09-28T10:00:50Z'))
        for point in action._data_entries[0:5]:
            self.assertEqual(point.status, 'cln')

        action._actual_first_id = 5
        action._actual_last_id = 10
        time0 = time.time()
        action.process()
        exec_time2 = time.time() - time0
        self.assertEqual(len(action._data_entries), 6)

        # The second process command should not do any commits so should be a lot faster
        # print(exec_time1, exec_time2)
        self.assertTrue(exec_time2 < exec_time1)

        # base_ts for this block is 2016-09-28T09:53:00Z which is sent time from first report - 60sec
        self.assertEqual(action._data_entries[0].timestamp, parse_datetime('2016-09-28T10:00:12Z'))
        self.assertEqual(action._data_entries[1].timestamp, parse_datetime('2016-09-28T10:00:20Z'))
        self.assertEqual(action._data_entries[2].timestamp, parse_datetime('2016-09-28T10:00:30Z'))
        self.assertEqual(action._data_entries[3].timestamp, parse_datetime('2016-09-28T10:00:40Z'))
        self.assertEqual(action._data_entries[4].timestamp, parse_datetime('2016-09-28T10:00:50Z'))
        for point in action._data_entries[0:5]:
            self.assertEqual(point.status, 'cln')

