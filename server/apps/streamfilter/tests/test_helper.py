import dateutil.parser
import datetime

from django.test import TestCase
from django.core.cache import cache

from apps.physicaldevice.models import Device
from apps.stream.models import StreamVariable, StreamId
from apps.streamdata.models import StreamData
from apps.utils.test_util import TestMixin
from apps.streamdata.helpers import StreamDataBuilderHelper

from ..models import *
from ..actions.action import *
from ..process import FilterHelper
from ..cache_utils import cached_serialized_filter_for_slug, get_current_cached_filter_state_for_slug
from ..processing.trigger import evaluate_cached_transition

from ..serializers import *


class StreamFilterHelperTestCase(TestMixin, TestCase):
    """
    Fixure includes:
    """

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=1,
        )
        self.v2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p2, created_by=self.u3, lid=2,
        )
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)
        self.s1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=self.pd1, created_by=self.u2
        )
        self.s2 = StreamId.objects.create_stream(
            project=self.p2, variable=self.v2, device=self.pd1, created_by=self.u3
        )
        if cache:
            cache.clear()

    def tearDown(self):
        StreamFilterAction.objects.all().delete()
        StreamFilterTrigger.objects.all().delete()
        StateTransition.objects.all().delete()
        StreamFilter.objects.all().delete()
        State.objects.all().defer()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        StreamData.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

        if cache:
            cache.clear()

    def _dummy_basic_filter(self, with_actions=False):
        """
        Filter with two states:
        state1 -> state2 if value >= 10
        state2 -> state1 if value < 10

        """
        f = StreamFilter.objects.create_filter_from_streamid(
            name='Filter 1', input_stream=self.s1, created_by=self.u2
        )
        a1 = a2 = None
        state1 = State.objects.create(label="state1", filter=f, created_by=self.u2)
        state2 = State.objects.create(label="state2", filter=f, created_by=self.u2)
        if with_actions:
            extra_payload = {
                "notification_recipient": "admin",
                "notification_level": "warn",
                "custom_note": "dummy"
            }
            a1 = StreamFilterAction.objects.create(
                type='eml', created_by=self.u2, extra_payload=extra_payload, on='exit', state=state1
            )
            a2 = StreamFilterAction.objects.create(
                type='eml', created_by=self.u2, extra_payload=extra_payload, on='exit', state=state2
            )

        transition1 = StateTransition.objects.create(
            src=state1, dst=state2, filter=f, created_by=self.u2
        )
        t1 = StreamFilterTrigger.objects.create(
            operator='ge', created_by=self.u2, filter=f, threshold=10, transition=transition1
        )
        transition2 = StateTransition.objects.create(
            src=state2, dst=state1, filter=f, created_by=self.u2
        )
        t2 = StreamFilterTrigger.objects.create(
            operator='lt', created_by=self.u2, filter=f, threshold=10, transition=transition2
        )

        return {
            'filter': f,
            'states': [state1, state2],
            'transitions': [transition1, transition2]
        }


    def _dummy_data(self, stream_slug, data):
        count = 1
        data_entries = []
        data_helper = StreamDataBuilderHelper()

        for item in data:
            stream_data = data_helper.build_data_obj(
                stream_slug=stream_slug,
                streamer_local_id=count,
                timestamp=item[0],
                int_value=item[1]
            )
            data_entries.append(stream_data)

        return data_entries

    def testTransitionShouldExecute(self):
        filter_info = self._dummy_basic_filter()

        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')

        data_helper = StreamDataBuilderHelper()
        stream_data = data_helper.build_data_obj(
            stream_slug=self.s1.slug,
            streamer_local_id=1,
            timestamp=t0,
            int_value=11
        )

        filter_helper = FilterHelper(False)

        serializer = StateTransitionReadOnlySerializer(filter_info['transitions'][0])
        transition1_data = serializer.data

        serializer = StateReadOnlySerializer(filter_info['transitions'][0].src)
        src = serializer.data
        serializer = StateReadOnlySerializer(filter_info['transitions'][0].dst)
        dst = serializer.data

        # No current state, but condition not met
        stream_data.value = 9
        res = filter_helper._transition_should_execute(
            src, dst, None, transition1_data, stream_data
        )
        self.assertFalse(res)

        # No current state, and condition met
        stream_data.value = 11
        res = filter_helper._transition_should_execute(
            src, dst, None, transition1_data, stream_data
        )
        self.assertTrue(res)

        # Different src state. Never transition
        res = filter_helper._transition_should_execute(
            src, dst, 'state2', transition1_data, stream_data
        )
        self.assertFalse(res)

        # Correct src state, does not meet condition
        stream_data.value = 9
        res = filter_helper._transition_should_execute(
            src, dst, 'state1', transition1_data, stream_data
        )
        self.assertFalse(res)

        # Correct src state, meet condition
        stream_data.value = 11
        res = filter_helper._transition_should_execute(
            src, dst, 'state1', transition1_data, stream_data
        )
        self.assertTrue(res)

        # No src, but condition not met
        stream_data.value = 9
        res = filter_helper._transition_should_execute(
            None, dst, 'state1', transition1_data, stream_data
        )
        self.assertFalse(res)

        # No src, and from another state. Condition met
        stream_data.value = 11
        res = filter_helper._transition_should_execute(
            None, dst, 'state1', transition1_data, stream_data
        )
        self.assertTrue(res)

        # No src, condition met from existing state
        stream_data.value = 11
        res = filter_helper._transition_should_execute(
            None, dst, 'state2', transition1_data, stream_data
        )
        self.assertFalse(res)

        # No src, condition met from existing state
        stream_data.value = 11
        res = filter_helper._transition_should_execute(
            None, dst, '', transition1_data, stream_data
        )
        self.assertTrue(res)

    def testBasic1Flow(self):

        filter_info = self._dummy_basic_filter()

        serializer = StateTransitionReadOnlySerializer(filter_info['transitions'][0])
        transition1_data = serializer.data
        serializer = StateTransitionReadOnlySerializer(filter_info['transitions'][1])
        transition2_data = serializer.data

        self.assertFalse(evaluate_cached_transition(transition1_data, 9))
        self.assertTrue(evaluate_cached_transition(transition2_data, 9))
        self.assertTrue(evaluate_cached_transition(transition1_data, 11))
        self.assertFalse(evaluate_cached_transition(transition2_data, 11))

        # 10 <= value < 20
        t3 = StreamFilterTrigger.objects.create(
            operator='lt', created_by=self.u2, filter=filter_info['filter'], threshold=20, transition=filter_info['transitions'][0]
        )
        serializer = StateTransitionReadOnlySerializer(filter_info['transitions'][0])
        transition1_data = serializer.data
        self.assertFalse(evaluate_cached_transition(transition1_data, 9))
        self.assertTrue(evaluate_cached_transition(transition1_data, 10))
        self.assertTrue(evaluate_cached_transition(transition1_data, 12))
        self.assertFalse(evaluate_cached_transition(transition1_data, 20))

    def testBasic2Flow(self):

        f = StreamFilter.objects.create_filter_from_streamid(
            name='Filter 1', input_stream=self.s1, created_by=self.u2
        )
        extra_payload = {
            "notification_recipient": "[org:admin]",
            "custom_note": "dummy"
        }
        state1 = State.objects.create(label="state1", filter=f, created_by=self.u2)
        state2 = State.objects.create(label="state2", filter=f, created_by=self.u2)
        a1 = StreamFilterAction.objects.create(
            type='eml', created_by=self.u2, extra_payload=extra_payload, on='exit', state=state1
        )
        a2 = StreamFilterAction.objects.create(
            type='eml', created_by=self.u2, extra_payload=extra_payload, on='entry', state=state1
        )
        transition1 = StateTransition.objects.create(
            src=state1, dst=state2, filter=f, created_by=self.u2
        )
        t1 = StreamFilterTrigger.objects.create(
            operator='ge', created_by=self.u2, filter=f, threshold=10, transition=transition1
        )
        transition2 = StateTransition.objects.create(
            src=state2, dst=state1, filter=f, created_by=self.u2
        )
        t2 = StreamFilterTrigger.objects.create(
            operator='lt', created_by=self.u2, filter=f, threshold=10, transition=transition2
        )

        cached_filter = cached_serialized_filter_for_slug(self.s1.slug)

        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        data = [
            (t0, 1),
            (t0 + datetime.timedelta(seconds=50), 5),
            (t0 + datetime.timedelta(seconds=100), 8),
            (t0 + datetime.timedelta(seconds=150), 11),
            (t0 + datetime.timedelta(seconds=200), 15),
            (t0 + datetime.timedelta(seconds=250), 9),
            (t0 + datetime.timedelta(seconds=300), 8),
            (t0 + datetime.timedelta(seconds=350), 12),
            (t0 + datetime.timedelta(seconds=400), 9),
        ]

        data_entries = self._dummy_data(self.s1.slug, data)

        filter_helper = FilterHelper(False)
        cached_filter = filter_helper.process_filter(data_entries[2], cached_filter)
        self.assertEqual(get_current_cached_filter_state_for_slug(self.s1.slug), 'state1')
        cached_filter = filter_helper.process_filter(data_entries[3], cached_filter)
        self.assertEqual(get_current_cached_filter_state_for_slug(self.s1.slug), 'state2')
        cached_filter = filter_helper.process_filter(data_entries[4], cached_filter)
        self.assertEqual(get_current_cached_filter_state_for_slug(self.s1.slug), 'state2')
        cached_filter = filter_helper.process_filter(data_entries[5], cached_filter)
        self.assertEqual(get_current_cached_filter_state_for_slug(self.s1.slug), 'state1')
