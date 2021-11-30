import json
import os

import dateutil.parser

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils.dateparse import parse_datetime

from apps.physicaldevice.models import Device
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.helpers import StreamDataBuilderHelper
from apps.streamdata.models import StreamData
from apps.streamer.models import *
from apps.streamer.serializers import *
from apps.streamer.worker.common.test_utils import create_test_data, get_reboot_slug
from apps.streamer.worker.v2_bin.process_report import ProcessReportV2Action
from apps.streamevent.models import StreamEventData
from apps.utils.iotile.streamer import STREAMER_SELECTOR
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import *
from apps.vartype.models import VarType, VarTypeDecoder

from ..cache_utils import get_current_cached_filter_state_for_slug
from ..models import *
from ..process import FilterHelper

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')

class StreamerV2FilterTestCase(TestMixin, TestCase):

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
        self.out_var1 = StreamVariable.objects.create_variable(
            name='Derived 1', project=self.p1, created_by=self.u2, lid=3,
        )
        self.out_var2 = StreamVariable.objects.create_variable(
            name='Derived 2', project=self.p1, created_by=self.u2, lid=4,
        )
        self.out_var3 = StreamVariable.objects.create_variable(
            name='Derived 3', project=self.p1, created_by=self.u2, lid=5,
        )
        self.out_stream1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.out_var1, device=self.pd1, created_by=self.u2
        )
        self.out_stream2 = StreamId.objects.create_stream(
            project=self.p1, variable=self.out_var2, device=self.pd1, created_by=self.u2
        )
        self.out_stream3 = StreamId.objects.create_stream(
            project=self.p1, variable=self.out_var3, device=self.pd1, created_by=self.u2
        )
        if cache:
            cache.clear()

    def tearDown(self):
        StreamFilterAction.objects.all().delete()
        StreamFilterTrigger.objects.all().delete()
        StateTransition.objects.all().delete()
        State.objects.all().defer()
        StreamFilter.objects.all().delete()
        StreamData.objects.all().delete()
        Streamer.objects.all().delete()
        StreamerReport.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasicFilterTriggerNoSrc(self):
        initial_state = ''

        f = StreamFilter.objects.create_filter_from_streamid(
            name='Filter 1', input_stream=self.s1, created_by=self.u2
        )
        state1 = State.objects.create(label="state1", filter=f, created_by=self.u2)
        state2 = State.objects.create(label="state2", filter=f, created_by=self.u2)
        a1 = StreamFilterAction.objects.create(
            type='drv', created_by=self.u2, on='entry', state=state1,
            extra_payload={'output_stream':self.out_stream1.slug}
        )
        a2 = StreamFilterAction.objects.create(
            type='drv', created_by=self.u2, on='entry', state=state2,
            extra_payload={'output_stream':self.out_stream2.slug}
        )
        transition1 = StateTransition.objects.create(
            dst=state2, filter=f, created_by=self.u2
        )
        t1 = StreamFilterTrigger.objects.create(
            operator='ge', created_by=self.u2, filter=f, threshold=10, transition=transition1
        )
        transition2 = StateTransition.objects.create(
            dst=state1, filter=f, created_by=self.u2
        )
        t2 = StreamFilterTrigger.objects.create(
            operator='lt', created_by=self.u2, filter=f, threshold=10, transition=transition2
        )

        action = ProcessReportV2Action()
        action._all_stream_filters = {}
        action._event_entries = []
        action._data_builder = StreamDataBuilderHelper()
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

        reboot_slug = get_reboot_slug(self.s1.project, self.s1.device, '5c00')
        stream_payload = [
            (self.s1.slug, 10, 5),  # transition2: '' -> state1
            (self.s1.slug, 20, 6),
            (self.s1.slug, 30, 7),
            (self.s1.slug, 40, 8),
            (self.s1.slug, 50, 9),
            (self.s1.slug, 60, 15), # transition1: state1 -> state2
            (self.s1.slug, 70, 16),
            (self.s1.slug, 80, 9),  # transitions2: state2 -> state1
            (self.s1.slug, 90, 8),
            (self.s1.slug, 100, 7),
        ]
        action._data_entries = create_test_data(action._data_builder, stream_payload, 5)
        action._handle_reboots_if_needed()
        self.assertEqual(len(action._data_entries), 10)
        action._count = len(action._data_entries)
        action._actual_first_id = action._data_entries[0]
        action._actual_last_id = action._data_entries[-1]

        action._post_read_stream_data()

        filter_helper = FilterHelper()
        filter_helper.process_filter_report(action._data_entries, action._all_stream_filters)

        self.assertEqual(len(action._data_entries), 10)
        self.assertEqual(StreamData.objects.count(), 3)
        self.assertEqual(StreamData.objects.filter(stream_slug=self.out_stream1.slug).count(), 2)
        self.assertEqual(StreamData.objects.filter(stream_slug=self.out_stream2.slug).count(), 1)

        self.assertEqual(get_current_cached_filter_state_for_slug(self.s1.slug), 'state1')

    def testBasicFilterTriggerTempExample(self):
        f = StreamFilter.objects.create_filter_from_streamid(
            name='Filter 1', input_stream=self.s1, created_by=self.u2
        )
        state1 = State.objects.create(label="hot", filter=f, created_by=self.u2)
        state2 = State.objects.create(label="ok", filter=f, created_by=self.u2)
        state3 = State.objects.create(label="cold", filter=f, created_by=self.u2)
        a1 = StreamFilterAction.objects.create(
            type='drv', created_by=self.u2, on='entry', state=state1,
            extra_payload={'output_stream':self.out_stream1.slug}
        )
        a2 = StreamFilterAction.objects.create(
            type='drv', created_by=self.u2, on='entry', state=state2,
            extra_payload={'output_stream':self.out_stream2.slug}
        )
        a3 = StreamFilterAction.objects.create(
            type='drv', created_by=self.u2, on='entry', state=state3,
            extra_payload={'output_stream':self.out_stream3.slug}
        )
        transition1 = StateTransition.objects.create(
            dst=state1, filter=f, created_by=self.u2
        )
        StreamFilterTrigger.objects.create(
            operator='ge', created_by=self.u2, filter=f, threshold=70, transition=transition1
        )
        transition2 = StateTransition.objects.create(
            dst=state2, filter=f, created_by=self.u2
        )
        StreamFilterTrigger.objects.create(
            operator='lt', created_by=self.u2, filter=f, threshold=70, transition=transition2
        )
        StreamFilterTrigger.objects.create(
            operator='gt', created_by=self.u2, filter=f, threshold=60, transition=transition2
        )
        transition3 = StateTransition.objects.create(
            dst=state3, filter=f, created_by=self.u2
        )
        StreamFilterTrigger.objects.create(
            operator='le', created_by=self.u2, filter=f, threshold=60, transition=transition3
        )

        action = ProcessReportV2Action()
        action._all_stream_filters = {}
        action._event_entries = []
        action._data_builder = StreamDataBuilderHelper()
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

        reboot_slug = get_reboot_slug(self.s1.project, self.s1.device, '5c00')
        stream_payload = [
            (self.s1.slug, 10, 50),  # transition1: '' -> state1
            (self.s1.slug, 20, 60),
            (self.s1.slug, 30, 65),  # transition2: state1 -> state2
            (self.s1.slug, 40, 67),
            (self.s1.slug, 50, 69),
            (self.s1.slug, 60, 70),  # transition3: state2 -> state3
            (self.s1.slug, 70, 72),
            (self.s1.slug, 80, 59),  # transitions1: state3 -> state1
            (self.s1.slug, 90, 75),  # transitions1: state1 -> state3
            (self.s1.slug, 100, 76),
        ]
        action._data_entries = create_test_data(action._data_builder, stream_payload, 5)
        action._handle_reboots_if_needed()
        self.assertEqual(len(action._data_entries), 10)
        action._count = len(action._data_entries)
        action._actual_first_id = action._data_entries[0]
        action._actual_last_id = action._data_entries[-1]

        action._post_read_stream_data()

        filter_helper = FilterHelper()
        filter_helper.process_filter_report(action._data_entries, action._all_stream_filters)

        self.assertEqual(len(action._data_entries), 10)
        self.assertEqual(StreamData.objects.count(), 5)
        self.assertEqual(StreamData.objects.filter(stream_slug=self.out_stream1.slug).count(), 2)
        self.assertEqual(StreamData.objects.filter(stream_slug=self.out_stream2.slug).count(), 1)
        self.assertEqual(StreamData.objects.filter(stream_slug=self.out_stream3.slug).count(), 2)

        self.assertEqual(get_current_cached_filter_state_for_slug(self.s1.slug), 'hot')

    def testProjectFilterTriggerNoSrc(self):
        f = StreamFilter.objects.create_filter_from_project_and_variable(
            name='Filter 1', proj=self.s1.project, var=self.s1.variable,
            created_by=self.u2
        )
        state1 = State.objects.create(label="state1", filter=f, created_by=self.u2)
        state2 = State.objects.create(label="state2", filter=f, created_by=self.u2)
        a1 = StreamFilterAction.objects.create(
            type='drv', created_by=self.u2, on='entry', state=state1,
            extra_payload={'output_stream':self.out_stream1.slug}
        )
        a2 = StreamFilterAction.objects.create(
            type='drv', created_by=self.u2, on='entry', state=state2,
            extra_payload={'output_stream':self.out_stream2.slug}
        )
        transition1 = StateTransition.objects.create(
            dst=state2, filter=f, created_by=self.u2
        )
        t1 = StreamFilterTrigger.objects.create(
            operator='ge', created_by=self.u2, filter=f, threshold=10, transition=transition1
        )
        transition2 = StateTransition.objects.create(
            dst=state1, filter=f, created_by=self.u2
        )
        t2 = StreamFilterTrigger.objects.create(
            operator='lt', created_by=self.u2, filter=f, threshold=10, transition=transition2
        )

        action = ProcessReportV2Action()
        action._all_stream_filters = {}
        action._event_entries = []
        action._data_builder = StreamDataBuilderHelper()
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

        reboot_slug = get_reboot_slug(self.s1.project, self.s1.device, '5c00')
        stream_payload = [
            (self.s1.slug, 10, 5),  # transition2: '' -> state1
            (self.s1.slug, 20, 6),
            (self.s1.slug, 30, 7),
            (self.s1.slug, 40, 8),
            (self.s1.slug, 50, 9),
            (self.s1.slug, 60, 15), # transition1: state1 -> state2
            (self.s1.slug, 70, 16),
            (self.s1.slug, 80, 9),  # transitions2: state2 -> state1
            (self.s1.slug, 90, 8),
            (self.s1.slug, 100, 7),
        ]
        action._data_entries = create_test_data(action._data_builder, stream_payload, 5)
        action._handle_reboots_if_needed()
        self.assertEqual(len(action._data_entries), 10)
        action._count = len(action._data_entries)
        action._actual_first_id = action._data_entries[0]
        action._actual_last_id = action._data_entries[-1]

        action._post_read_stream_data()

        filter_helper = FilterHelper()
        filter_helper.process_filter_report(action._data_entries, action._all_stream_filters)

        self.assertEqual(len(action._data_entries), 10)
        self.assertEqual(StreamData.objects.count(), 3)
        self.assertEqual(StreamData.objects.filter(stream_slug=self.out_stream1.slug).count(), 2)
        self.assertEqual(StreamData.objects.filter(stream_slug=self.out_stream2.slug).count(), 1)

        self.assertEqual(get_current_cached_filter_state_for_slug(self.s1.slug), 'state1')

