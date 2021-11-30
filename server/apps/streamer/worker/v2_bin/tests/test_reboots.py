import json
import os

import dateutil.parser

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils.dateparse import parse_datetime

from apps.physicaldevice.models import Device
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.helpers import StreamDataBuilderHelper
from apps.streamdata.models import StreamData
from apps.streamer.models import *
from apps.streamer.serializers import *
from apps.streamevent.models import StreamEventData
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import *
from apps.vartype.models import VarType, VarTypeDecoder

from ...common.test_utils import create_test_data, get_reboot_slug
from ..process_report import ProcessReportV2Action

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')

class StreamerV2RebootsTestCase(TestMixin, TestCase):

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

    def testNoReboot(self):
        action = ProcessReportV2Action()
        action._received_dt = parse_datetime('2016-09-28T10:00:00Z')
        action._streamer = self.user_streamer1
        action._device = self.pd1
        action._streamer_report = StreamerReport.objects.create(streamer=self.user_streamer1,
                                                                original_first_id=5,
                                                                original_last_id=9,
                                                                device_sent_timestamp=120,
                                                                sent_timestamp=action._received_dt,
                                                                incremental_id=10,
                                                                created_by=self.u1 )

        helper = StreamDataBuilderHelper()
        stream_payload = [
            (self.s1.slug, 10, 5),
            (self.s1.slug, 20, 6),
            (self.s1.slug, 30, 7),
            (self.s1.slug, 40, 8),
            (self.s1.slug, 50, 9),
        ]
        action._data_entries = create_test_data(helper, stream_payload, 5)
        self.assertEqual(len(action._data_entries), 5)
        action._handle_reboots_if_needed()

        self.assertEqual(action._data_entries[0].timestamp, parse_datetime('2016-09-28T09:58:10Z'))
        self.assertEqual(action._data_entries[4].timestamp, parse_datetime('2016-09-28T09:58:50Z'))

        for point in action._data_entries:
            self.assertEqual(point.status, 'cln')

    def testOneReboot(self):
        action = ProcessReportV2Action()
        action._received_dt = parse_datetime('2016-09-28T10:00:00Z')
        action._streamer = self.user_streamer1
        action._device = self.pd1
        StreamerReport.objects.create(streamer=self.user_streamer1,
                                      original_first_id=2,
                                      original_last_id=3,
                                      actual_last_id=3,
                                      device_sent_timestamp=60,
                                      incremental_id=4,
                                      sent_timestamp=parse_datetime('2016-09-28T09:56:00Z'),
                                      created_by=self.u1 )
        action._streamer_report = StreamerReport.objects.create(streamer=self.user_streamer1,
                                                                original_first_id=5,
                                                                original_last_id=12,
                                                                device_sent_timestamp=240,
                                                                sent_timestamp=action._received_dt,
                                                                incremental_id=14,
                                                                created_by=self.u1 )

        helper = StreamDataBuilderHelper()
        reboot_slug = get_reboot_slug(self.s1.project, self.s1.device, '5c00')
        stream_payload = [
            (self.s1.slug, 10, 5),
            (self.s1.slug, 20, 6),
            (self.s1.slug, 30, 7),
            (self.s1.slug, 40, 8),
            (self.s1.slug, 50, 9),
            (reboot_slug, 2, 1),
            (self.s1.slug, 10, 5),
            (self.s1.slug, 20, 6),
        ]
        action._data_entries = create_test_data(helper, stream_payload, 5)
        self.assertEqual(len(action._data_entries), 8)
        action._handle_reboots_if_needed()

        self.assertEqual(action._data_entries[0].timestamp, parse_datetime('2016-09-28T09:55:10Z'))
        self.assertEqual(action._data_entries[1].timestamp, parse_datetime('2016-09-28T09:55:20Z'))
        self.assertEqual(action._data_entries[2].timestamp, parse_datetime('2016-09-28T09:55:30Z'))
        self.assertEqual(action._data_entries[3].timestamp, parse_datetime('2016-09-28T09:55:40Z'))
        self.assertEqual(action._data_entries[4].timestamp, parse_datetime('2016-09-28T09:55:50Z'))
        self.assertEqual(action._data_entries[5].timestamp, parse_datetime('2016-09-28T09:56:02Z'))
        self.assertEqual(action._data_entries[6].timestamp, parse_datetime('2016-09-28T09:56:10Z'))
        self.assertEqual(action._data_entries[7].timestamp, parse_datetime('2016-09-28T09:56:20Z'))

        for point in action._data_entries:
            self.assertEqual(point.status, 'cln')

    def testTwoReboot(self):
        action = ProcessReportV2Action()
        action._received_dt = parse_datetime('2016-09-28T10:00:00Z')
        action._streamer = self.user_streamer1
        action._device = self.pd1
        StreamerReport.objects.create(streamer=self.user_streamer1,
                                      original_first_id=2,
                                      original_last_id=3,
                                      actual_last_id=3,
                                      device_sent_timestamp=60,
                                      incremental_id=4,
                                      sent_timestamp=parse_datetime('2016-09-28T09:54:00Z'),
                                      created_by=self.u1 )
        action._streamer_report = StreamerReport.objects.create(streamer=self.user_streamer1,
                                                                original_first_id=5,
                                                                original_last_id=12,
                                                                device_sent_timestamp=240,
                                                                sent_timestamp=action._received_dt,
                                                                incremental_id=14,
                                                                created_by=self.u1 )

        helper = StreamDataBuilderHelper()
        reboot_slug = get_reboot_slug(self.s1.project, self.s1.device, '5c00')
        stream_payload = [
            (self.s1.slug, 10, 5),
            (self.s1.slug, 20, 6),
            (self.s1.slug, 30, 7),
            (self.s1.slug, 40, 8),
            (self.s1.slug, 50, 9),
            (reboot_slug, 2, 1),
            (self.s1.slug, 10, 15),
            (self.s1.slug, 20, 16),
            (reboot_slug, 2, 1),
            (self.s1.slug, 10, 25),
            (self.s1.slug, 20, 26),
            (self.s1.slug, 30, 27),
        ]
        action._data_entries = create_test_data(helper, stream_payload, 5)
        action._handle_reboots_if_needed()
        self.assertEqual(len(action._data_entries), 12)

        # base_ts for this block is 2016-09-28T09:53:00Z which is sent time from first report - 60sec
        self.assertEqual(action._data_entries[0].timestamp, parse_datetime('2016-09-28T09:53:10Z'))
        self.assertEqual(action._data_entries[1].timestamp, parse_datetime('2016-09-28T09:53:20Z'))
        self.assertEqual(action._data_entries[2].timestamp, parse_datetime('2016-09-28T09:53:30Z'))
        self.assertEqual(action._data_entries[3].timestamp, parse_datetime('2016-09-28T09:53:40Z'))
        self.assertEqual(action._data_entries[4].timestamp, parse_datetime('2016-09-28T09:53:50Z'))
        for point in action._data_entries[0:5]:
            self.assertEqual(point.status, 'cln')

        # base_ts for this block is 2016-09-28T09:55:39Z which is base_ts of next report minus 20 minus extra 1
        self.assertEqual(action._data_entries[5].timestamp, parse_datetime('2016-09-28T09:55:41Z'))
        self.assertEqual(action._data_entries[6].timestamp, parse_datetime('2016-09-28T09:55:49Z'))
        self.assertEqual(action._data_entries[7].timestamp, parse_datetime('2016-09-28T09:55:59Z'))
        for point in action._data_entries[5:8]:
            self.assertEqual(point.status, 'drt')

        # base_ts for this block is 2016-09-28T09:56:02Z
        self.assertEqual(action._data_entries[8].timestamp, parse_datetime('2016-09-28T09:56:02Z'))
        self.assertEqual(action._data_entries[9].timestamp, parse_datetime('2016-09-28T09:56:10Z'))
        self.assertEqual(action._data_entries[10].timestamp, parse_datetime('2016-09-28T09:56:20Z'))
        self.assertEqual(action._data_entries[11].timestamp, parse_datetime('2016-09-28T09:56:30Z'))

        for point in action._data_entries[8:12]:
            self.assertEqual(point.status, 'cln')

    def testRebootsWithNoPreviousReports(self):
        action = ProcessReportV2Action()
        action._received_dt = parse_datetime('2016-09-28T10:00:00Z')
        action._streamer = self.user_streamer1
        action._device = self.pd1
        action._streamer_report = StreamerReport.objects.create(streamer=self.user_streamer1,
                                                                original_first_id=5,
                                                                original_last_id=16,
                                                                device_sent_timestamp=240,
                                                                sent_timestamp=action._received_dt,
                                                                incremental_id=14,
                                                                created_by=self.u1 )

        helper = StreamDataBuilderHelper()
        reboot_slug = get_reboot_slug(self.s1.project, self.s1.device, '5c00')
        stream_payload = [
            (self.s1.slug, 10, 5),
            (self.s1.slug, 20, 6),
            (self.s1.slug, 30, 7),
            (self.s1.slug, 40, 8),
            (self.s1.slug, 50, 9),
            (reboot_slug, 2, 1),
            (self.s1.slug, 10, 15),
            (self.s1.slug, 20, 16),
            (reboot_slug, 2, 1),
            (self.s1.slug, 10, 25),
            (self.s1.slug, 20, 26),
            (self.s1.slug, 30, 27),
        ]
        action._data_entries = create_test_data(helper, stream_payload, 5)
        action._handle_reboots_if_needed()
        self.assertEqual(len(action._data_entries), 12)

        # base_ts for this block is 2016-09-28T09:54:58Z which comes from next block minus 50sec minus extra 1
        self.assertEqual(action._data_entries[0].timestamp, parse_datetime('2016-09-28T09:54:58Z'))
        self.assertEqual(action._data_entries[1].timestamp, parse_datetime('2016-09-28T09:55:08Z'))
        self.assertEqual(action._data_entries[2].timestamp, parse_datetime('2016-09-28T09:55:18Z'))
        self.assertEqual(action._data_entries[3].timestamp, parse_datetime('2016-09-28T09:55:28Z'))
        self.assertEqual(action._data_entries[4].timestamp, parse_datetime('2016-09-28T09:55:38Z'))
        for point in action._data_entries[0:5]:
            self.assertEqual(point.status, 'drt')

        # base_ts for this block is 2016-09-28T09:55:39Z which is base_ts of next report minus 20 minus extra 1
        self.assertEqual(action._data_entries[5].timestamp, parse_datetime('2016-09-28T09:55:41Z'))
        self.assertEqual(action._data_entries[6].timestamp, parse_datetime('2016-09-28T09:55:49Z'))
        self.assertEqual(action._data_entries[7].timestamp, parse_datetime('2016-09-28T09:55:59Z'))
        for point in action._data_entries[5:8]:
            self.assertEqual(point.status, 'drt')

        # base_ts for this block is 2016-09-28T09:56:02Z
        self.assertEqual(action._data_entries[8].timestamp, parse_datetime('2016-09-28T09:56:02Z'))
        self.assertEqual(action._data_entries[9].timestamp, parse_datetime('2016-09-28T09:56:10Z'))
        self.assertEqual(action._data_entries[10].timestamp, parse_datetime('2016-09-28T09:56:20Z'))
        self.assertEqual(action._data_entries[11].timestamp, parse_datetime('2016-09-28T09:56:30Z'))
        for point in action._data_entries[8:12]:
            self.assertEqual(point.status, 'cln')

    def testRemovingRebootsFromUserReport(self):
        action = ProcessReportV2Action()
        action._received_dt = parse_datetime('2016-09-28T10:00:00Z')
        action._streamer = self.user_streamer1
        action._device = self.pd1
        action._streamer_report = StreamerReport.objects.create(streamer=self.user_streamer1,
                                                                original_first_id=5,
                                                                original_last_id=16,
                                                                device_sent_timestamp=240,
                                                                sent_timestamp=action._received_dt,
                                                                incremental_id=14,
                                                                created_by=self.u1)

        helper = StreamDataBuilderHelper()
        reboot_slug = get_reboot_slug(self.s1.project, self.s1.device, '5c00')
        stream_payload = [
            (self.s1.slug, 10, 5),
            (self.s1.slug, 20, 6),
            (self.s1.slug, 30, 7),
            (self.s1.slug, 40, 8),
            (self.s1.slug, 50, 9),
            (reboot_slug, 2, 1),
            (self.s1.slug, 10, 15),
            (self.s1.slug, 20, 16),
            (reboot_slug, 2, 1),
            (self.s1.slug, 10, 25),
            (self.s1.slug, 20, 26),
            (self.s1.slug, 30, 27),
        ]
        action._data_entries = create_test_data(helper, stream_payload, 5)
        action._data_builder = helper
        action._actual_first_id = action._data_entries[0].incremental_id
        action._actual_last_id = action._data_entries[-1].incremental_id
        action._count = len(action._data_entries)

        action._post_read_stream_data()
        self.assertEqual(len(action._data_entries), 10)

        for point in action._data_entries:
            self.assertNotEqual(point.stream_slug, reboot_slug)

        self.assertEqual(action._data_entries[0].timestamp, parse_datetime('2016-09-28T09:54:58Z'))
        self.assertEqual(action._data_entries[1].timestamp, parse_datetime('2016-09-28T09:55:08Z'))
        self.assertEqual(action._data_entries[2].timestamp, parse_datetime('2016-09-28T09:55:18Z'))
        self.assertEqual(action._data_entries[3].timestamp, parse_datetime('2016-09-28T09:55:28Z'))
        self.assertEqual(action._data_entries[4].timestamp, parse_datetime('2016-09-28T09:55:38Z'))
        self.assertEqual(action._data_entries[5].timestamp, parse_datetime('2016-09-28T09:55:49Z'))
        self.assertEqual(action._data_entries[6].timestamp, parse_datetime('2016-09-28T09:55:59Z'))
        self.assertEqual(action._data_entries[7].timestamp, parse_datetime('2016-09-28T09:56:10Z'))
        self.assertEqual(action._data_entries[8].timestamp, parse_datetime('2016-09-28T09:56:20Z'))
        self.assertEqual(action._data_entries[9].timestamp, parse_datetime('2016-09-28T09:56:30Z'))

    def testKeepingRebootsOnSystemReport(self):
        action = ProcessReportV2Action()
        action._received_dt = parse_datetime('2016-09-28T10:00:00Z')
        action._device = self.pd1
        action._streamer = Streamer.objects.create(device=self.pd1, index=1, created_by=self.u2,
                                                   selector=STREAMER_SELECTOR['SYSTEM'], process_engine_ver=2)
        action._streamer_report = StreamerReport.objects.create(streamer=action._streamer,
                                                                original_first_id=5,
                                                                original_last_id=16,
                                                                device_sent_timestamp=240,
                                                                sent_timestamp=action._received_dt,
                                                                incremental_id=14,
                                                                created_by=self.u1)

        helper = StreamDataBuilderHelper()
        reboot_slug = get_reboot_slug(self.s1.project, self.s1.device, '5c00')
        other_slug = get_reboot_slug(self.s1.project, self.s1.device, '5c01')
        stream_payload = [
            (other_slug, 10, 5),
            (other_slug, 20, 6),
            (other_slug, 30, 7),
            (other_slug, 40, 8),
            (other_slug, 50, 9),
            (reboot_slug, 2, 1),
            (other_slug, 10, 15),
            (other_slug, 20, 16),
            (reboot_slug, 2, 1),
            (other_slug, 10, 25),
            (other_slug, 20, 26),
            (other_slug, 30, 27),
        ]
        action._data_entries = create_test_data(helper, stream_payload, 5)
        action._data_builder = helper
        action._actual_first_id = action._data_entries[0].incremental_id
        action._actual_last_id = action._data_entries[-1].incremental_id
        action._count = len(action._data_entries)

        action._post_read_stream_data()
        self.assertEqual(len(action._data_entries), 12)

        self.assertEqual(action._data_entries[5].stream_slug, reboot_slug)
        self.assertEqual(action._data_entries[8].stream_slug, reboot_slug)

        # base_ts for this block is 2016-09-28T09:54:58Z which comes from next block minus 50sec minus extra 1
        self.assertEqual(action._data_entries[0].timestamp, parse_datetime('2016-09-28T09:54:58Z'))
        self.assertEqual(action._data_entries[1].timestamp, parse_datetime('2016-09-28T09:55:08Z'))
        self.assertEqual(action._data_entries[2].timestamp, parse_datetime('2016-09-28T09:55:18Z'))
        self.assertEqual(action._data_entries[3].timestamp, parse_datetime('2016-09-28T09:55:28Z'))
        self.assertEqual(action._data_entries[4].timestamp, parse_datetime('2016-09-28T09:55:38Z'))
        for point in action._data_entries[0:5]:
            self.assertEqual(point.status, 'drt')

        # base_ts for this block is 2016-09-28T09:55:39Z which is base_ts of next report minus 20 minus extra 1
        self.assertEqual(action._data_entries[5].timestamp, parse_datetime('2016-09-28T09:55:41Z'))
        self.assertEqual(action._data_entries[6].timestamp, parse_datetime('2016-09-28T09:55:49Z'))
        self.assertEqual(action._data_entries[7].timestamp, parse_datetime('2016-09-28T09:55:59Z'))
        for point in action._data_entries[5:8]:
            self.assertEqual(point.status, 'drt')

        # base_ts for this block is 2016-09-28T09:56:02Z
        self.assertEqual(action._data_entries[8].timestamp, parse_datetime('2016-09-28T09:56:02Z'))
        self.assertEqual(action._data_entries[9].timestamp, parse_datetime('2016-09-28T09:56:10Z'))
        self.assertEqual(action._data_entries[10].timestamp, parse_datetime('2016-09-28T09:56:20Z'))
        self.assertEqual(action._data_entries[11].timestamp, parse_datetime('2016-09-28T09:56:30Z'))
        for point in action._data_entries[8:12]:
            self.assertEqual(point.status, 'cln')

    def testRebootWithDoubleReport(self):
        action = ProcessReportV2Action()
        action._received_dt = parse_datetime('2016-09-28T10:00:00Z')
        action._streamer = self.user_streamer1
        action._device = self.pd1
        StreamerReport.objects.create(streamer=self.user_streamer1,
                                      original_first_id=2,
                                      original_last_id=3,
                                      actual_last_id=3,
                                      device_sent_timestamp=60,
                                      incremental_id=3,
                                      sent_timestamp=parse_datetime('2016-09-28T09:56:00Z'),
                                      created_by=self.u1 )
        StreamerReport.objects.create(streamer=self.user_streamer1,
                                      original_first_id=5,
                                      original_last_id=12,
                                      actual_last_id=0,
                                      device_sent_timestamp=250,
                                      incremental_id=14,
                                      sent_timestamp=parse_datetime('2016-09-28T09:56:22Z'),
                                      created_by=self.u1 )
        action._streamer_report = StreamerReport.objects.create(streamer=self.user_streamer1,
                                                                original_first_id=5,
                                                                original_last_id=12,
                                                                device_sent_timestamp=240,
                                                                sent_timestamp=action._received_dt,
                                                                incremental_id=15,
                                                                created_by=self.u1 )

        helper = StreamDataBuilderHelper()
        reboot_slug = get_reboot_slug(self.s1.project, self.s1.device, '5c00')
        stream_payload = [
            (self.s1.slug, 10, 5),
            (self.s1.slug, 20, 6),
            (self.s1.slug, 30, 7),
            (self.s1.slug, 40, 8),
            (self.s1.slug, 50, 9),
            (reboot_slug, 2, 1),
            (self.s1.slug, 10, 5),
            (self.s1.slug, 20, 6),
        ]
        action._data_entries = create_test_data(helper, stream_payload, 5)
        self.assertEqual(len(action._data_entries), 8)
        action._handle_reboots_if_needed()

        self.assertEqual(action._data_entries[0].timestamp, parse_datetime('2016-09-28T09:55:10Z'))
        self.assertEqual(action._data_entries[1].timestamp, parse_datetime('2016-09-28T09:55:20Z'))
        self.assertEqual(action._data_entries[2].timestamp, parse_datetime('2016-09-28T09:55:30Z'))
        self.assertEqual(action._data_entries[3].timestamp, parse_datetime('2016-09-28T09:55:40Z'))
        self.assertEqual(action._data_entries[4].timestamp, parse_datetime('2016-09-28T09:55:50Z'))
        self.assertEqual(action._data_entries[5].timestamp, parse_datetime('2016-09-28T09:56:02Z'))
        self.assertEqual(action._data_entries[6].timestamp, parse_datetime('2016-09-28T09:56:10Z'))
        self.assertEqual(action._data_entries[7].timestamp, parse_datetime('2016-09-28T09:56:20Z'))

        for point in action._data_entries:
            self.assertEqual(point.status, 'cln')

    def testTripStartEndException(self):
        action = ProcessReportV2Action()
        action._received_dt = parse_datetime('2018-05-18T17:20:00Z')
        action._streamer = Streamer.objects.create(device=self.pd2, index=2, created_by=self.u3,
                                selector=STREAMER_SELECTOR['TRIP_SYSTEM'], process_engine_ver=2)
        action._device = self.pd1
        StreamerReport.objects.create(streamer=self.user_streamer1,
                                      original_first_id=5,
                                      original_last_id=8,
                                      actual_last_id=8,
                                      device_sent_timestamp=240,
                                      incremental_id=4,
                                      sent_timestamp=parse_datetime('2018-05-18T17:20:00Z'),
                                      created_by=self.u1 )
        action._streamer_report = StreamerReport.objects.create(streamer=self.user_streamer1,
                                                                original_first_id=5,
                                                                original_last_id=8,
                                                                device_sent_timestamp=240,
                                                                sent_timestamp=action._received_dt,
                                                                incremental_id=14,
                                                                created_by=self.u1 )

        helper = StreamDataBuilderHelper()
        reboot_slug = get_reboot_slug(self.s1.project, self.s1.device, '5c00')
        start_slug = get_reboot_slug(self.s1.project, self.s1.device, '0e00')
        end_slug = get_reboot_slug(self.s1.project, self.s1.device, '0e01')
        record_slug = get_reboot_slug(self.s1.project, self.s1.device, '0e02')
        stream_entries = [
            helper.build_data_obj(
                stream_slug=start_slug,
                device_timestamp=7729,
                timestamp=parse_datetime('2018-04-30T02:17:44Z'),
                streamer_local_id=5,
                int_value=1525056046
            ),
            helper.build_data_obj(
                stream_slug=record_slug,
                device_timestamp=7729,
                timestamp=parse_datetime('2018-06-18T17:19:02Z'),
                streamer_local_id=6,
                int_value=0
            ),
            helper.build_data_obj(
                stream_slug=record_slug,
                device_timestamp=1030,
                timestamp=parse_datetime('2018-05-18T17:19:02Z'),
                streamer_local_id=7,
                int_value=1
            ),
            helper.build_data_obj(
                stream_slug=end_slug,
                device_timestamp=1030,
                timestamp=parse_datetime('2018-05-18T17:19:02Z'),
                streamer_local_id=8,
                int_value=1526663957
            )
        ]
        action._data_entries = stream_entries
        self.assertEqual(len(action._data_entries), 4)
        action._handle_reboots_if_needed()

        self.assertEqual(datetime.datetime.fromtimestamp(1525056046, datetime.timezone.utc),
                         parse_datetime('2018-04-30T02:40:46Z'))
        self.assertEqual(action._data_entries[0].timestamp, parse_datetime('2018-04-30T02:40:46Z'))

        self.assertEqual(action._data_entries[1].timestamp, parse_datetime('2018-04-30T02:40:46Z'))
        self.assertEqual(action._data_entries[2].timestamp, parse_datetime('2018-04-30T02:57:56Z'))

        self.assertEqual(datetime.datetime.fromtimestamp(1526663957, datetime.timezone.utc),
                         parse_datetime('2018-05-18T17:19:17Z'))
        self.assertEqual(action._data_entries[3].timestamp, parse_datetime('2018-05-18T17:19:17Z'))

    def testOneRebootUTCTimestamp(self):
        action = ProcessReportV2Action()
        action._received_dt = parse_datetime('2016-09-28T10:00:00Z')
        action._streamer = self.user_streamer1
        action._device = self.pd1
        StreamerReport.objects.create(streamer=self.user_streamer1,
                                      original_first_id=2,
                                      original_last_id=3,
                                      actual_last_id=3,
                                      device_sent_timestamp=60,
                                      incremental_id=4,
                                      sent_timestamp=parse_datetime('2016-09-28T09:56:00Z'),
                                      created_by=self.u1 )
        action._streamer_report = StreamerReport.objects.create(streamer=self.user_streamer1,
                                                                original_first_id=5,
                                                                original_last_id=12,
                                                                device_sent_timestamp=240,
                                                                sent_timestamp=action._received_dt,
                                                                incremental_id=14,
                                                                created_by=self.u1 )

        helper = StreamDataBuilderHelper()
        reboot_slug = get_reboot_slug(self.s1.project, self.s1.device, '5c00')
        stream_payload = [
            (self.s1.slug, 10, 5),
            (self.s1.slug, 20, 6),
            (self.s1.slug, 30, 7),
            (self.s1.slug, 40, 8),
            (self.s1.slug, 50, 9),
            (reboot_slug, 2, 1),
            (self.s1.slug, 550000100 | (1 << 31), 5),
            (self.s1.slug, 550000200 | (1 << 31), 6),
        ]
        action._data_entries = create_test_data(helper, stream_payload, 5)
        self.assertEqual(len(action._data_entries), 8)
        action._handle_reboots_if_needed()

        self.assertEqual(action._data_entries[0].timestamp, parse_datetime('2016-09-28T09:55:10Z'))
        self.assertEqual(action._data_entries[1].timestamp, parse_datetime('2016-09-28T09:55:20Z'))
        self.assertEqual(action._data_entries[2].timestamp, parse_datetime('2016-09-28T09:55:30Z'))
        self.assertEqual(action._data_entries[3].timestamp, parse_datetime('2016-09-28T09:55:40Z'))
        self.assertEqual(action._data_entries[4].timestamp, parse_datetime('2016-09-28T09:55:50Z'))
        self.assertEqual(action._data_entries[5].timestamp, parse_datetime('2016-09-28T09:56:02Z'))
        self.assertEqual(action._data_entries[6].timestamp, parse_datetime('2017-06-05T17:48:20Z'))
        self.assertEqual(action._data_entries[7].timestamp, parse_datetime('2017-06-05T17:50:00Z'))

        for point in action._data_entries[6:]:
            self.assertEqual(point.status, 'utc')



