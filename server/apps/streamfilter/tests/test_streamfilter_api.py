
from unittest import mock

from apps.physicaldevice.models import Device
from apps.stream.models import StreamVariable, StreamId
from apps.streamdata.utils import get_stream_output_mdo
from apps.streamdata.models import StreamData
from apps.utils.test_util import TestMixin
from apps.vartype.models import VarType, VarTypeOutputUnit
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.utils.gid.convert import formatted_gfid
from ..actions.action import *
from ..cache_utils import *
from ..dynamodb import *
from ..process import FilterHelper
from ..serializers import *

user_model = get_user_model()


class StreamFilterAPITests(TestMixin, APITestCase):

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
            project=self.p1, variable=self.v2, device=self.pd1, created_by=self.u2
        )
        self.out_var1 = StreamVariable.objects.create_variable(
            name='Derived 1', project=self.p2, created_by=self.u2, lid=3,
        )
        self.out_var2 = StreamVariable.objects.create_variable(
            name='Derived 2', project=self.p2, created_by=self.u2, lid=4,
        )
        self.out_var3 = StreamVariable.objects.create_variable(
            name='Derived 3', project=self.p2, created_by=self.u2, lid=5,
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

    def _setupFixure(self, op, threshold, in_stream, out_stream, user):
        f = StreamFilter.objects.create_filter_from_streamid(name='{0} {1}'.format(op, threshold),
                                                             input_stream=in_stream,
                                                             created_by=user)
        state1 = State.objects.create(label="state1", filter=f, created_by=self.u2)
        state2 = State.objects.create(label="state2", filter=f, created_by=self.u2)
        a = StreamFilterAction.objects.create(
            type='drv', created_by=self.u2, on='entry', state=state1,
            extra_payload={'output_stream':out_stream.slug}
        )
        a2 = StreamFilterAction.objects.create(
            type='cus', created_by=self.u2, on='entry', state=state2
        )
        transition = StateTransition.objects.create(src=state1, dst=state2, filter=f, created_by=self.u2)
        t = StreamFilterTrigger.objects.create(
            operator=op, user_threshold=threshold, created_by=user, filter=f, transition=transition
        )

        return f, t, a, state1, state2, transition

    def testActionSerializer(self):
        f, t, a, state1, state2, transition = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        serializer = StreamFilterActionSerializer(a)
        data = serializer.data
        self.assertEqual(data['type'], 'drv')
        self.assertEqual(data['extra_payload']['output_stream'], self.out_stream1.slug)

    def testTriggerSerializer(self):
        f, t, a, state1, state2, transition = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        serializer = StreamFilterTriggerSerializer(t)
        data = serializer.data
        self.assertEqual(data['operator'], 'bu')
        self.assertEqual(data['user_threshold'], 10)

    def testFilterSerializer(self):
        f, t, a, state1, state2, transition = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        self.assertEqual(t.filter, f)
        serializer = StreamFilterSerializer(f)
        data = serializer.data
        self.assertEqual(data['slug'].split('--')[0], 'f')
        self.assertEqual(data['slug'].split('--')[1:], self.s1.slug.split('--')[1:])
        self.assertEqual(data['input_stream'], self.s1.slug)
        self.assertTrue(data['active'])
        transitions = data['transitions']
        self.assertEqual(len(transitions), 1)
        t1 = transitions[0]['triggers'][0]
        self.assertEqual(t1['operator'], 'bu')
        self.assertEqual(t1['user_threshold'], 10)
        src = transitions[0]['src']
        states = data['states']
        actions = None
        for s in states:
            if s['id'] == src:
                actions = s['actions']
        self.assertEqual(actions[0]['type'], 'drv')
        self.assertEqual(actions[0]['extra_payload']['output_stream'], self.out_stream1.slug)

    def testFilterGetAll(self):
        f, t, a, state1, state2, transition = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        f2, t2, a2, state1, state2, transition = self._setupFixure('bu', 1, self.s2, self.out_stream2, self.u2)

        url = reverse('streamfilter-list')

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)
        data_list = deserialized['results']
        self.assertEqual(len(data_list), 2)
        data = data_list[0]
        self.assertEqual(data['slug'].split('--')[0], 'f')
        self.assertTrue(data['active'])
        transitions = data['transitions']
        self.assertEqual(len(transitions), 1)
        t1 = transitions[0]['triggers'][0]
        self.assertEqual(t1['operator'], 'bu')
        self.assertEqual(t1['user_threshold'], 10)
        states = data['states']
        src = transitions[0]['src']
        actions = None
        for s in states:
            if s['id'] == src:
                actions = s['actions']
        self.assertEqual(actions[0]['type'], 'drv')
        self.assertEqual(actions[0]['extra_payload']['output_stream'], self.out_stream1.slug)
        self.client.logout()

    def testFilterGetOne(self):
        f1, t1, a1, state1, state2, transition = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)

        url = reverse('streamfilter-detail', kwargs={'slug': f1.slug})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = json.loads(resp.content.decode())
        self.assertEqual(data['slug'].split('--')[0], 'f')
        self.assertEqual(data['slug'].split('--')[1:], self.s1.slug.split('--')[1:])
        self.assertEqual(data['input_stream'], self.s1.slug)
        self.assertTrue(data['active'])
        transitions = data['transitions']
        self.assertEqual(len(transitions), 1)
        t1 = transitions[0]['triggers'][0]
        self.assertEqual(t1['operator'], 'bu')
        self.assertEqual(t1['user_threshold'], 10)
        states = data['states']
        src = transitions[0]['src']
        actions = None
        for s in states:
            if s['id'] == src:
                actions = s['actions']
        self.assertEqual(actions[0]['type'], 'drv')
        self.assertEqual(actions[0]['extra_payload']['output_stream'], self.out_stream1.slug)

        self.client.logout()

    def testFilterGetBadSlug(self):
        f1, t1, a1, state1, state2, transition = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)

        url = reverse('streamfilter-detail', kwargs={'slug': self.pd1})

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

    def testFilterCreate(self):
        url = reverse('streamfilter-list')

        resp = self.client.post(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            "project": str(self.p1.slug),
            "name": "My test filter",
            "device": self.pd1.slug
        }

        resp = self.client.post(url, data=payload, format='json')
        data = json.loads(resp.content.decode())
        self.assertEqual(len(data), 1)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(data['variable'][0], "This field is required.")

        payload = {
            "name": "My test filter",
            "variable": self.v1.slug,
            "device": self.pd1.slug
        }

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        data = json.loads(resp.content.decode())
        self.assertEqual(len(data), 1)
        self.assertEqual(data['project'][0], "This field is required.")

        payload = {
            "name": "My test filter",
            "project": str(self.p1.slug),
            "variable": "not-id",
            "device": self.pd1.slug
        }

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        data = json.loads(resp.content.decode())
        self.assertEqual(len(data), 1)
        self.assertEqual(data['variable'][0], "Object with slug=not-id does not exist.")

        payload = {
            "name": "My test filter",
            "project": str(self.p1.slug),
            "variable": self.v1.slug,
            "device": self.pd1.slug
        }

        self.assertEqual(StreamFilter.objects.all().count(), 0)
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamFilter.objects.all().count(), 1)
        f = StreamFilter.objects.all().first()
        self.assertEqual(f.name, "My test filter")
        expected_slug = formatted_gfid(pid=self.p1.formatted_gid,
                                       did=self.pd1.formatted_gid,
                                       vid=self.v1.formatted_lid)
        self.assertEqual(f.slug, expected_slug)
        self.assertEqual(f.variable, self.v1)
        self.assertEqual(f.project, self.p1)
        self.assertEqual(f.device, self.pd1)
        self.assertEqual(f.input_stream, self.s1)

        payload = {
            "name": "My test filter",
            "project": str(self.p1.slug),
            "variable": self.v1.slug,
            "device": self.pd1.slug
        }

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        data = json.loads(resp.content.decode())
        self.assertEqual(len(data), 1)
        self.assertEqual(data['non_field_errors'][0], "Filter for this stream already exists")

        payload = {
            "name": "My project filter",
            "project": str(self.p1.slug),
            "variable": self.v1.slug,
        }

        self.assertEqual(StreamFilter.objects.all().count(), 1)
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamFilter.objects.all().count(), 2)
        f = StreamFilter.objects.all().last()
        self.assertEqual(f.name, "My project filter")
        expected_slug = formatted_gfid(pid=self.p1.formatted_gid,
                                       did=None,
                                       vid=self.v1.formatted_lid)
        self.assertEqual(f.slug, expected_slug)
        self.assertEqual(f.variable, self.v1)
        self.assertEqual(f.project, self.p1)
        self.assertEqual(f.device, None)
        self.assertEqual(f.input_stream, None)

        payload = {
            "name": "My project filter",
            "project": str(self.p1.slug),
            "variable": self.v1.slug,
        }

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        data = json.loads(resp.content.decode())
        self.assertEqual(len(data), 1)
        self.assertEqual(data['non_field_errors'][0], "Filter already exists")

    def testGetState(self):
        f1, t1, a1, state11, state12, transition1 = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        f2, t2, a2, state21, state22, transition2 = self._setupFixure('bu', 10, self.s2, self.out_stream2, self.u2)

        url = reverse('streamfilter-state', kwargs={'slug': f1.slug})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = json.loads(resp.content.decode())

        self.assertEqual(len(data), 2)
        self.assertEqual(data[0], StateReadOnlySerializer(state11).data)
        self.assertEqual(data[1], StateReadOnlySerializer(state12).data)

    def testPostCreateState(self):
        f1, t1, a1, state11, state12, transition1 = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        f2, t2, a2, state21, state22, transition2 = self._setupFixure('bu', 10, self.s2, self.out_stream2, self.u2)

        url = reverse('streamfilter-state', kwargs={'slug': f1.slug})

        resp = self.client.post(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            "label": state11.label,
        }

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        data = json.loads(resp.content.decode())
        self.assertEqual(len(data), 1)
        self.assertEqual(data['non_field_errors'][0], "State already exists")

        payload = {
            "label": "New State",
        }

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = json.loads(resp.content.decode())
        self.assertEqual(data['label'], "New State")
        self.assertEqual(data['actions'], [])
        self.assertEqual(State.objects.filter(filter=f1, label="New State").count(), 1)

        payload = {
            "label": "New State 2",
        }

        resp = self.client.post(url, data=payload, format='json')
        data = json.loads(resp.content.decode())
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(data['label'], "New State 2")
        self.assertEqual(data['actions'], [])
        self.assertEqual(State.objects.filter(filter=f1, label="New State 2").count(), 1)

    def testDeleteState(self):
        f1, t1, a1, state11, state12, transition1 = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        f2, t2, a2, state21, state22, transition2 = self._setupFixure('bu', 10, self.s2, self.out_stream2, self.u2)

        url = reverse('streamfilter-state', kwargs={'slug': f1.slug})

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            "label": "not a state label"
        }

        resp = self.client.delete(url, data=payload, format='json')
        data = json.loads(resp.content.decode())
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        payload = {
            "label": state11.label
        }

        resp = self.client.delete(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(State.objects.filter(filter=f1, label="state1").count(), 0)

    def testPutUpdateState(self):
        f1, t1, a1, state11, state12, transition1 = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        f2, t2, a2, state21, state22, transition2 = self._setupFixure('bu', 10, self.s2, self.out_stream2, self.u2)

        url = reverse('streamfilter-state', kwargs={'slug': f1.slug})

        resp = self.client.put(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            "label": "Not a state label",
        }

        resp = self.client.put(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        payload = {
            "label": state11.label,
        }

        state = State.objects.get(filter=f1, label="state1")
        self.assertEqual(state.entry_action_qs.count(), 1)
        self.assertEqual(state.exit_action_qs.count(), 0)

        resp = self.client.put(url, data=payload, format='json')
        data = json.loads(resp.content.decode())
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(data['label'], "state1")
        self.assertIsNotNone(data['actions'])
        state = State.objects.get(filter=f1, label="state1")
        self.assertEqual(state.entry_action_qs.count(), 1)
        self.assertEqual(state.exit_action_qs.count(), 0)

    def testGetTransition(self):
        f1, t1, a1, state11, state12, transition1 = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        f2, t2, a2, state21, state22, transition2 = self._setupFixure('bu', 10, self.s2, self.out_stream2, self.u2)

        url = reverse('streamfilter-transition', kwargs={'slug': f1.slug})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = json.loads(resp.content.decode())

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['id'], str(transition1.id))
        self.assertEqual(data[0]['src'], StateReadOnlySerializer(state11).data['id'])
        self.assertEqual(data[0]['dst'], StateReadOnlySerializer(state12).data['id'])
        self.assertEqual(len(data[0]['triggers']), 1)
        self.assertEqual(data[0]['triggers'][0]['id'], t1.id)

    def testPostCreateTransition(self):
        f1, t1, a1, state11, state12, transition1 = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        f2, t2, a2, state21, state22, transition2 = self._setupFixure('bu', 10, self.s2, self.out_stream2, self.u2)

        url = reverse('streamfilter-transition', kwargs={'slug': f1.slug})

        resp = self.client.post(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            "src": state22.id,
            "dst": state21.id,
        }

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        data = json.loads(resp.content.decode())
        self.assertEqual(len(data), 1)
        self.assertEqual(data['non_field_errors'][0], "Src and dst must be states of the filter in serializer context")

        payload = {
            "src": state22.id,
            "dst": state11.id,
        }

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        data = json.loads(resp.content.decode())
        self.assertEqual(len(data), 1)
        self.assertEqual(data['non_field_errors'][0], "Src and dst must be states of the filter in serializer context")

        payload = {
            "src": state11.id,
            "dst": state12.id,
        }

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        data = json.loads(resp.content.decode())
        self.assertEqual(len(data), 1)
        self.assertEqual(data['non_field_errors'][0], "Transition already exists")

        payload = {
            "src": state12.id,
            "dst": state11.id,
        }

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = json.loads(resp.content.decode())
        self.assertEqual(data['src'], state12.id)
        self.assertEqual(data['dst'], state11.id)
        self.assertEqual(StateTransition.objects.filter(filter=f1, src=state12, dst=state11).count(), 1)

        payload = {
            "src": state22.id,
            "dst": state21.id,
            "triggers": [
                {
                    "operator": "ge",
                    "user_threshold": 10
                }
            ]
        }
        self.assertEqual(StreamFilterTrigger.objects.all().count(), 2)
        url = reverse('streamfilter-transition', kwargs={'slug': f2.slug})
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(StreamFilterTrigger.objects.all().count(), 3)
        data = json.loads(resp.content.decode())
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(data['src'], state22.id)
        self.assertEqual(data['dst'], state21.id)
        self.assertEqual(StateTransition.objects.filter(filter=f2, src=state22, dst=state21).count(), 1)
        new_transition = StateTransition.objects.get(filter=f2, src=state22, dst=state21)
        self.assertEqual(new_transition.triggers.all().count(), 1)
        trigger = new_transition.triggers.all()[0]
        self.assertEqual(trigger.operator, "ge")
        self.assertEqual(trigger.user_threshold, 10)
        self.assertEqual(trigger.filter, f2)

    def testDeleteTransition(self):
        f1, t1, a1, state11, state12, transition1 = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        f2, t2, a2, state21, state22, transition2 = self._setupFixure('bu', 10, self.s2, self.out_stream2, self.u2)

        url = reverse('streamfilter-transition', kwargs={'slug': f1.slug})

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            "src": state12.id,
            "dst": state11.id,
        }

        resp = self.client.delete(url, data=payload, format='json')
        data = json.loads(resp.content.decode())
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        payload = {
            "src": state11.id,
            "dst": state12.id,
            "id": str(transition2.id)
        }

        resp = self.client.delete(url, data=payload, format='json')
        data = json.loads(resp.content.decode())
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        payload = {
            "src": state11.id,
            "dst": state12.id,
        }

        resp = self.client.delete(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(StateTransition.objects.filter(filter=f1).count(), 0)

    def testPutUpdateTransition(self):
        f1, t1, a1, state11, state12, transition1 = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        f2, t2, a2, state21, state22, transition2 = self._setupFixure('bu', 10, self.s2, self.out_stream2, self.u2)

        url = reverse('streamfilter-transition', kwargs={'slug': f1.slug})

        resp = self.client.put(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            "src": state12.id,
            "dst": state11.id,
            "triggers": [
                {
                    "operator": "le",
                    "user_threshold": 20
                }
            ]
        }

        resp = self.client.put(url, data=payload, format='json')
        data = json.loads(resp.content.decode())
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        payload = {
            "src": state11.id,
            "dst": state12.id,
            "triggers": [
                {
                    "operator": "le",
                    "user_threshold": 20
                }
            ]
        }
        self.assertEqual(StreamFilterTrigger.objects.all().count(), 2)
        url = reverse('streamfilter-transition', kwargs={'slug': f1.slug})
        resp = self.client.put(url, data=payload, format='json')
        self.assertEqual(StreamFilterTrigger.objects.all().count(), 2)
        data = json.loads(resp.content.decode())
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(data['src'], state11.id)
        self.assertEqual(data['dst'], state12.id)
        updated_transition = StateTransition.objects.get(filter=f1, src=state11, dst=state12)
        self.assertEqual(updated_transition.triggers.all().count(), 1)
        trigger = updated_transition.triggers.all()[0]
        self.assertEqual(trigger.operator, "le")
        self.assertEqual(trigger.user_threshold, 20)
        self.assertEqual(trigger.filter, f1)

    def testGetTrigger(self):
        f1, t1, a1, state11, state12, transition1 = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        f2, t2, a2, state21, state22, transition2 = self._setupFixure('bu', 10, self.s2, self.out_stream2, self.u2)

        url = reverse('streamfilter-trigger', kwargs={'slug': f1.slug})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = json.loads(resp.content.decode())

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['id'], t1.id)
        self.assertEqual(data[0]['operator'], "bu")
        self.assertEqual(data[0]['user_threshold'], 10)

    def testPostCreateTrigger(self):
        f1, t1, a1, state11, state12, transition1 = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        f2, t2, a2, state21, state22, transition2 = self._setupFixure('bu', 10, self.s2, self.out_stream2, self.u2)

        var_type = VarType.objects.create(
            name='Volume',
            storage_units_full='Liters',
            created_by=self.u2
        )

        output_unit1 = VarTypeOutputUnit.objects.create(
            var_type=var_type,
            unit_full='Liters',
            unit_short='l',
            m=1,
            d=2,
            created_by=self.u2
        )
        self.s1.output_unit = output_unit1
        self.s1.save()

        url = reverse('streamfilter-trigger', kwargs={'slug': f1.slug})

        resp = self.client.post(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            "transition": str(transition2.id),
            "operator": "ge",
            "user_threshold": 10
        }

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        data = json.loads(resp.content.decode())
        self.assertEqual(len(data), 1)
        self.assertEqual(data['non_field_errors'][0], "Invalid transition")

        payload = {
            "transition": str(transition1.id),
            "operator": "ge",
            "user_threshold": 10
        }

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = json.loads(resp.content.decode())

        output_mdo = get_stream_output_mdo(self.s1)

        self.assertEqual(data['operator'], "ge")
        self.assertEqual(data['get_operator_display'], "Greater or equal than (>=)")
        self.assertEqual(data['user_threshold'], 10)
        self.assertEqual(data['threshold'], output_mdo.compute_reverse(10))
        self.assertEqual(data['user_output_unit'], output_unit1.id)
        self.assertEqual(data['user_unit_full'], output_unit1.unit_full)

        self.assertEqual(StreamFilterTrigger.objects.filter(id=data['id'], transition=transition1, filter=f1).count(), 1)

    def testDeleteTrigger(self):
        f1, t1, a1, state11, state12, transition1 = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        f2, t2, a2, state21, state22, transition2 = self._setupFixure('bu', 10, self.s2, self.out_stream2, self.u2)

        url = reverse('streamfilter-trigger', kwargs={'slug': f1.slug})

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            "transition": str(t1.transition.id),
            "id": t2.id
        }

        resp = self.client.delete(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        payload = {
            "transition": str(t2.transition.id),
            "id": t1.id
        }

        resp = self.client.delete(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        payload = {
            "transition": str(t1.transition.id),
        }

        resp = self.client.delete(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        data = json.loads(resp.content.decode())
        self.assertEqual(data['error'], 'Trigger id is required')

        payload = {
            "transition": str(t1.transition.id),
            "id": t1.id
        }
        self.assertEqual(StreamFilterTrigger.objects.filter(filter=f1).count(), 1)
        resp = self.client.delete(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(StreamFilterTrigger.objects.filter(filter=f1).count(), 0)

    def testPostCreateAction(self):
        f1, t1, a1, state11, state12, transition1 = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        f2, t2, a2, state21, state22, transition2 = self._setupFixure('bu', 10, self.s2, self.out_stream2, self.u2)

        url = reverse('streamfilter-action', kwargs={'slug': f1.slug})

        resp = self.client.post(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            "state": state11.id,
            "on": "exit",
            "type": "cus",
            "extra_payload": json.dumps({"extra": "dummy"})
        }

        state11 = State.objects.get(id=state11.id)
        self.assertEqual(state11.actions.count(), 1)

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = json.loads(resp.content.decode())
        new_action = StreamFilterAction.objects.get(id=data['id'])
        state11 = State.objects.get(id=state11.id)
        self.assertEqual(state11.actions.count(), 2)
        self.assertEqual(state11.actions.filter(type='cus').count(), 1)
        self.assertEqual(state11.actions.filter(type='cus').first(), new_action)
        self.assertEqual(new_action.type, 'cus')
        self.assertEqual(new_action.extra_payload, json.dumps({"extra": "dummy"}))

    def testDeleteAction(self):
        f1, t1, a1, state11, state12, transition1 = self._setupFixure('bu', 10, self.s1, self.out_stream1, self.u2)
        f2, t2, a2, state21, state22, transition2 = self._setupFixure('bu', 10, self.s2, self.out_stream2, self.u2)

        url = reverse('streamfilter-action', kwargs={'slug': f1.slug})

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            "id": 1000
        }

        resp = self.client.delete(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        payload = {
            "type": "acu"
        }

        resp = self.client.delete(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        data = json.loads(resp.content.decode())
        self.assertEqual(data['error'], 'Action id is required')

        payload = {
            "id": a1.id
        }

        state11 = State.objects.get(filter=f1, slug=state11.slug)
        state12 = State.objects.get(filter=f1, slug=state12.slug)
        self.assertEqual(state11.actions.count(), 1)
        self.assertEqual(state12.actions.count(), 1)
        self.assertEqual(StreamFilterAction.objects.all().count(), 4)
        resp = self.client.delete(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(StreamFilterAction.objects.all().count(), 3)
        state11 = State.objects.get(filter=f1, slug=state11.slug)
        state12 = State.objects.get(filter=f1, slug=state12.slug)
        self.assertEqual(state11.actions.count(), 0)
        self.assertEqual(state12.actions.count(), 1)

