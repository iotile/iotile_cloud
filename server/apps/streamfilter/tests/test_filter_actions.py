from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django.core.cache import cache

from apps.physicaldevice.models import Device
from apps.stream.models import StreamVariable, StreamId
from apps.streamdata.utils import get_stream_output_mdo
from apps.streamdata.models import StreamData
from apps.utils.test_util import TestMixin
from apps.vartype.models import VarType, VarTypeOutputUnit

from ..models import *
from ..actions.factory import action_factory
from ..process import FilterHelper
from ..serializers import *


class StreamFilterActionsTestCase(TestMixin, TestCase):
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
        StreamFilter.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

        if cache:
            cache.clear()

    def testEmlActions(self):
        f = StreamFilter.objects.create_filter_from_streamid(name='filter 1',
                                                             input_stream=self.s1,
                                                             created_by=self.u2)

        data = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=10,
            value=10.34689543760,
        )
        action = {
            'id': 1,
            'type': 'eml',
        }
        action_obj = action_factory(action['type'])
        payload = {
            'on': 'exit',
            'action': action,
            'state': {"label": "STATE"},
            'transition': {"triggers": [], "src": 1, "dst": 2},
            'filter': f.slug
        }
        result = action_obj.process(payload=payload, in_data=data)
        self.assertFalse(result)

        # Backwards compatible: Old payload
        action['extra_payload'] = {
            'notification_recipient': {
                'org': 'admin'
            },
            'notification_level': 'warn',
            'custom_note': 'custom'
        }
        payload = {
            'on': 'exit',
            'action': action,
            'state': {"label": "STATE"},
            'transition': {"triggers": [], "src": 1, "dst": 2},
            'filter': f.slug
        }
        result = action_obj.process(payload=payload, in_data=data)
        self.assertTrue(result)

        if cache:
            cache.clear()

        # Backwards compatible: Old payload
        action['extra_payload'] = {
            'notification_recipient': {
                'users': ['user1', 'user2']
            },
            'custom_note': 'custom'
        }
        payload = {
            'on': 'exit',
            'action': action,
            'state': {"label": "STATE"},
            'transition': {"triggers": [], "src": 1, "dst": 2},
            'filter': f.slug
        }
        result = action_obj.process(payload=payload, in_data=data)
        self.assertTrue(result)

        if cache:
            cache.clear()

        action['extra_payload'] = {
            'notification_recipient': ['user:user1'],
            'body': 'Transitioning to {state} for {device}'
        }
        payload = {
            'on': 'exit',
            'action': action,
            'state': {"label": "STATE"},
            'transition': {"triggers": [], "src": 1, "dst": 2},
            'filter': f.slug
        }
        result = action_obj.process(payload=payload, in_data=data)
        self.assertTrue(result)

    @mock.patch('apps.streamfilter.actions.slk_action.action.SlkAction.Slack.send')
    def testSlkActionsForProject(self, mock_send_slack):
        mock_send_slack.return_value = None
        f = StreamFilter.objects.create_filter_from_project_and_variable(
            name='filter 1', proj=self.s1.project, var=self.s1.variable, created_by=self.u2
        )
        data = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=10,
            value=10.34689543760
        )
        action = {
            'id': 1,
            'type': 'slk',
        }
        action_obj = action_factory(action['type'])

        # Missing extra_payload
        payload = {
            'on': 'exit',
            'action': action,
            'state': {"label": "STATE"},
            'transition': {"triggers": [], "src": None, "dst": 1},
            'filter': f.slug
        }
        result = action_obj.process(payload=payload, in_data=data)
        self.assertFalse(result)

        # Missing fields in extra payload
        action['extra_payload'] = {
            'notification_recipient': 'admin',
        }

        result = action_obj.process(payload=payload, in_data=data)
        self.assertFalse(result)

        # success
        action['extra_payload'] = {
            'custom_note': 'custom',
            'slack_webhook': 'http://foo.bar'
        }
        payload = {
            'on': 'exit',
            'action': action,
            'state': {"label": "STATE"},
            'transition': {"triggers": [], "src": 1, "dst": 2},
            'filter': f.slug

        }
        result = action_obj.process(payload=payload, in_data=data)
        self.assertTrue(result)

    @mock.patch('apps.streamfilter.actions.slk_action.action.SlkAction.Slack.send')
    def testSlkActionsForStream(self, mock_send_slack):
        mock_send_slack.return_value = None
        f = StreamFilter.objects.create_filter_from_streamid(name='filter 1',
                                                             input_stream=self.s1,
                                                             created_by=self.u2)
        data = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=10,
            value=10.34689543760
        )
        action = {
            'id': 1,
            'type': 'slk',
        }
        action_obj = action_factory(action['type'])

        # Missing extra_payload
        payload = {
            'on': 'exit',
            'action': action,
            'state': {"label": "STATE"},
            'transition': {"triggers": [], "src": None, "dst": 1},
            'filter': f.slug
        }
        result = action_obj.process(payload=payload, in_data=data)
        self.assertFalse(result)

        # Missing fields in extra payload
        action['extra_payload'] = {
            'notification_recipient': 'admin',
        }

        result = action_obj.process(payload=payload, in_data=data)
        self.assertFalse(result)

        # success
        action['extra_payload'] = {
            'custom_note': 'custom',
            'slack_webhook': 'http://foo.bar'
        }
        payload = {
            'on': 'exit',
            'action': action,
            'state': {"label": "STATE"},
            'transition': {"triggers": [], "src": None, "dst": 1},
            'filter': f.slug

        }
        result = action_obj.process(payload=payload, in_data=data)
        self.assertTrue(result)

    def testDrvActions(self):
        f = StreamFilter.objects.create_filter_from_streamid(name='filter 1',
                                                             input_stream=self.s1,
                                                             created_by=self.u2)
        state1 = State.objects.create(label="state1", filter=f, created_by=self.u2)
        state2 = State.objects.create(label="state2", filter=f, created_by=self.u2)
        a = StreamFilterAction.objects.create(
            type='drv', created_by=self.u2, on='exit', state=state1,
            extra_payload={'output_stream':self.s2.slug}
        )
        transition = StateTransition.objects.create(src=state1, dst=state2, filter=f, created_by=self.u2)
        t = StreamFilterTrigger.objects.create(operator='bu', user_threshold=0, created_by=self.u2, filter=f, transition=transition)

        data = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=10
        )
        serializer = StreamFilterActionSerializer(a)
        action = serializer.data
        action_obj = action_factory(action['type'])

        # Missing field
        payload = {
            'action': action,
            'state': StateSerializer(state1).data,
            'transition': StateTransitionSerializer(transition).data,
            'filter': f.slug
        }
        result = action_obj.process(payload=payload, in_data=data)
        self.assertFalse(result)

        payload = {
            'on': 'exit',
            'action': action,
            'state': StateSerializer(state1).data,
            'transition': StateTransitionSerializer(transition).data,
            'filter': f.slug

        }
        self.assertEqual(StreamData.objects.filter(stream_slug=self.s2.slug).count(), 0)

        helper = FilterHelper()
        filter_serializer = StreamFilterSerializer(f)
        filter_data = filter_serializer.data
        helper.process_filter(data, filter_data)
        helper._create_derived_data()
        self.assertEqual(StreamData.objects.filter(stream_slug=self.s2.slug).count(), 1)
        derived_data = StreamData.objects.filter(stream_slug=self.s2.slug).first()
        self.assertEqual(derived_data.stream_slug, self.s2.slug)
        self.assertEqual(derived_data.timestamp, data.timestamp)
        self.assertEqual(derived_data.int_value, 10)

    @mock.patch('apps.utils.sms.helper.SmsHelper.send')
    def testSmsAction(self, sms_mock):

        f = StreamFilter.objects.create_filter_from_project_and_variable(
            name='filter 1', proj=self.s1.project, var=self.s1.variable, created_by=self.u2
        )
        data = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=10,
            value=10.34689543760
        )
        action = {
            'id': 1,
            'type': 'sms',
        }
        action_obj = action_factory(action['type'])

        # Missing extra_payload
        payload = {
            'on': 'exit',
            'action': action,
            'state': {"label": "STATE"},
            'transition': {"triggers": [], "src": None, "dst": 1},
            'filter': f.slug
        }
        result = action_obj.process(payload=payload, in_data=data)
        self.assertFalse(result)

        # Missing fields in extra payload
        action['extra_payload'] = {
            'number': '+16505551234',
        }

        result = action_obj.process(payload=payload, in_data=data)
        self.assertFalse(result)

        # Bad number
        sms_mock.return_value = False, "Unable to create record: The 'To' number +1650555 is not a valid phone number."

        action['extra_payload'] = {
            'number': '+1650555',
            'body': '{device}: {label} transitioned {on} state {state}: {ts} -> {value}'
        }
        payload = {
            'on': 'exit',
            'action': action,
            'state': {"label": "STATE"},
            'transition': {"triggers": [], "src": 1, "dst": 2},
            'filter': f.slug

        }
        result = action_obj.process(payload=payload, in_data=data)
        self.assertFalse(result)

        # success
        sms_mock.return_value = True, 'SMf54fbb4ebc354e1981ccc2427e29dd46'
        action['extra_payload'] = {
            'number': '+16505551122',
            'body': '{label} transitioned {on} state {state}: {ts} -> {value}'
        }
        payload = {
            'on': 'exit',
            'action': action,
            'state': {"label": "STATE"},
            'transition': {"triggers": [], "src": 1, "dst": 2},
            'filter': f.slug

        }
        result = action_obj.process(payload=payload, in_data=data)
        self.assertTrue(result)

    """ ENABLE TO TEST TWILIO SEND FOR REAL (only on local machine)
    def testSmsAction2(self):

        f = StreamFilter.objects.create_filter_from_project_and_variable(
            name='filter 1', proj=self.s1.project, var=self.s1.variable, created_by=self.u2
        )
        data = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=10,
            value=10.34689543760
        )
        action = {
            'id': 1,
            'type': 'sms',
        }
        action_obj = action_factory(action['type'])

        action['extra_payload'] = {
            'number': '+NUM',
            'body': '{label} transitioned {on} state {state}: {ts} -> {value}'
        }
        payload = {
            'on': 'exit',
            'action': action,
            'state': {"label": "STATE"},
            'transition': {"triggers": [], "src": 1, "dst": 2},
            'filter': f.slug

        }
        result = action_obj.process(payload=payload, in_data=data)
        self.assertTrue(result)
    """

