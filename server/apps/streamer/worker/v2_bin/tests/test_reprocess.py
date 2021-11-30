import json
import os
from unittest import mock, skipIf

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
from apps.utils.iotile.variable import ENCODED_STREAM_VALUES
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import *
from apps.vartype.models import VarType, VarTypeDecoder

from ...common.test_utils import create_test_data, get_reboot_slug
from ..process_report import ProcessReportV2Action
from ..reprocess_data import ReProcessDataV2Action

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')

class StreamerV2ReprocessTestCase(TestMixin, TestCase):

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

    def _add_dummy_encoded_data(self, stream, ts, dts, sigid, data):
        helper = StreamDataBuilderHelper()
        result = []

        result.append(helper.build_data_obj(
            stream_slug=stream.slug,
            type='Num',
            device_timestamp=dts,
            streamer_local_id=sigid,
            timestamp=ts,
            int_value=ENCODED_STREAM_VALUES['BEGIN']
        ))
        sigid += 1
        for item in data:
            result.append(helper.build_data_obj(
                stream_slug=stream.slug,
                type='Num',
                device_timestamp=dts,
                streamer_local_id=sigid,
                timestamp=ts,
                int_value=item
            ))
            sigid += 1

        result.append(helper.build_data_obj(
            stream_slug=stream.slug,
            type='Num',
            device_timestamp=dts,
            streamer_local_id=sigid,
            timestamp=ts,
            int_value=ENCODED_STREAM_VALUES['END']
        ))
        sigid += 1

        return result

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
        action = ReProcessDataV2Action()
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
        action = ReProcessDataV2Action()
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
                                                                original_last_id=17,
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
        entries = create_test_data(helper, stream_payload, 5)
        StreamData.objects.bulk_create(entries)
        self.assertEqual(StreamData.objects.count(), 12)

        action._actual_first_id = 5
        action._actual_last_id = 17
        action.process()
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

        action._streamer_report.sent_timestamp = parse_datetime('2016-10-28T10:00:00Z')
        action.process()
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
        self.assertEqual(action._data_entries[5].timestamp, parse_datetime('2016-10-28T09:55:41Z'))
        self.assertEqual(action._data_entries[6].timestamp, parse_datetime('2016-10-28T09:55:49Z'))
        self.assertEqual(action._data_entries[7].timestamp, parse_datetime('2016-10-28T09:55:59Z'))
        for point in action._data_entries[5:8]:
            self.assertEqual(point.status, 'drt')

        # base_ts for this block is 2016-09-28T09:56:02Z
        self.assertEqual(action._data_entries[8].timestamp, parse_datetime('2016-10-28T09:56:02Z'))
        self.assertEqual(action._data_entries[9].timestamp, parse_datetime('2016-10-28T09:56:10Z'))
        self.assertEqual(action._data_entries[10].timestamp, parse_datetime('2016-10-28T09:56:20Z'))
        self.assertEqual(action._data_entries[11].timestamp, parse_datetime('2016-10-28T09:56:30Z'))

        for point in action._data_entries[8:12]:
            self.assertEqual(point.status, 'cln')

    def testEncodingData(self):
        action = ReProcessDataV2Action()
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
                                                                original_last_id=17,
                                                                device_sent_timestamp=240,
                                                                sent_timestamp=action._received_dt,
                                                                incremental_id=14,
                                                                created_by=self.u1 )
        var_type = VarType.objects.create(
            name='Accelerometer',
            storage_units_full='Encoded',
            created_by=self.u1
        )
        VarTypeDecoder.objects.create(var_type=var_type, created_by=self.u1,
                                      raw_packet_format='<LLLL',
                                      packet_info={
                                          'decoding': [
                                              "H{axis:2,peak:14}",
                                              "H{duration}",
                                              "l{delta_v_x}",
                                              "l{delta_v_y}",
                                              "l{delta_v_z}",
                                          ]
                                        })
        self.assertIsNotNone(var_type.decoder)

        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        data = [0x05000026, 0xFFFFFFFB, 0x20, 0x5]
        StreamId.objects.all().delete()
        self.assertEqual(StreamData.objects.count(), 0)
        self.s1 = StreamId.objects.create(device=self.pd1, variable=self.v1, project=self.p2, var_type=var_type,
                                          created_by=self.u2, mdo_type = 'V')
        self.assertTrue(self.s1.is_encoded)
        data_stream = self._add_dummy_encoded_data(stream=self.s1, ts=t0, dts=20, sigid=5, data=data)
        self.assertEqual(len(data_stream), 6)
        StreamData.objects.bulk_create(data_stream)
        self.assertEqual(StreamData.objects.count(), 6)

        action._actual_first_id = data_stream[0].streamer_local_id
        action._actual_last_id = data_stream[-1].streamer_local_id
        action.process()

        event = StreamEventData.objects.all().order_by('streamer_local_id').last()
        self.assertIsNotNone(event)
        self.assertEqual(event.extra_data['axis'], 2)
        self.assertEqual(event.extra_data['peak'], 9)
        self.assertEqual(event.extra_data['duration'], 0x500)
        self.assertEqual(event.extra_data['delta_v_x'], -5)
        self.assertEqual(event.extra_data['delta_v_y'], 0x20)
        self.assertEqual(event.extra_data['delta_v_z'], 5)

        action._actual_first_id = data_stream[0].streamer_local_id
        action._actual_last_id = data_stream[-1].streamer_local_id
        action.process()

        event = StreamEventData.objects.all().order_by('streamer_local_id').last()
        self.assertIsNotNone(event)
        self.assertEqual(event.extra_data['axis'], 2)
        self.assertEqual(event.extra_data['peak'], 9)
        self.assertEqual(event.extra_data['duration'], 0x500)
        self.assertEqual(event.extra_data['delta_v_x'], -5)
        self.assertEqual(event.extra_data['delta_v_y'], 0x20)
        self.assertEqual(event.extra_data['delta_v_z'], 5)



