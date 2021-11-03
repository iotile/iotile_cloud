from django.contrib.auth import get_user_model
from django.test import TestCase
from django.core.cache import cache

from rest_framework import status
from rest_framework.reverse import reverse

from apps.physicaldevice.models import Device
from apps.stream.models import StreamVariable, StreamId
from apps.streamdata.utils import get_stream_output_mdo
from apps.streamdata.models import StreamData
from apps.utils.test_util import TestMixin
from apps.vartype.models import VarType, VarTypeOutputUnit

user_model = get_user_model()

from ..models import *


class StreamFilterViewTestCase(TestMixin, TestCase):
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

    def testStreamFilterProjectCreateView(self):
        url = reverse('org:project:filter-add', kwargs={"org_slug": self.p1.org.slug, "pk": str(self.p1.id)})
        payload = {
            "name": "test",
            "variable": self.v1.id,
            "states": "Green, Red, Blue",
            "submit": "Submit"
        }

        self.client.login(email='user1@foo.com', password='pass')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(StreamFilter.objects.all().count(), 0)
        resp = self.client.post(url, data=payload)
        self.assertEqual(StreamFilter.objects.all().count(), 1)
        f = StreamFilter.objects.all().first()
        self.assertRedirects(resp, expected_url=reverse("filter:detail", kwargs={'slug': f.slug}),
                             status_code=302,
                             target_status_code=200)
        self.assertEqual(f.project, self.p1)
        self.assertEqual(f.variable, self.v1)
        self.assertEqual(f.device, None)
        self.assertEqual(f.input_stream, None)
        self.assertEqual(f.name, "test")
        filter_project_key = '--'.join(['f', self.p1.formatted_gid, '', self.v1.formatted_lid])
        self.assertEqual(f.slug, filter_project_key)
        self.assertTrue(f.active)

        self.assertEqual(State.objects.filter(filter=f).count(), 3)
        self.assertEqual(State.objects.filter(filter=f, label="Green").count(), 1)
        self.assertEqual(State.objects.filter(filter=f, label="Red").count(), 1)
        self.assertEqual(State.objects.filter(filter=f, label="Blue").count(), 1)

        # Test duplicate variable filter
        payload = {
            "name": "test",
            "variable": self.v1.id,
            "states": "Green, Red, Blue",
            "submit": "Submit"
        }
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(StreamFilter.objects.all().count(), 1)
        self.assertFormError(resp, 'form', None, "Filter for this variable already exists")

        # test create filter for device
        payload = {
            "name": "test",
            "variable": self.v1.id,
            "device": self.pd1.id,
            "states": "Green, Red, Blue",
            "submit": "Submit"
        }

        self.client.login(email='user1@foo.com', password='pass')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(StreamFilter.objects.all().count(), 1)
        resp = self.client.post(url, data=payload)
        self.assertEqual(StreamFilter.objects.all().count(), 2)
        f = StreamFilter.objects.all().first()
        self.assertRedirects(resp, expected_url=reverse("filter:detail", kwargs={'slug': f.slug}),
                             status_code=302,
                             target_status_code=200)
        self.assertEqual(f.project, self.p1)
        self.assertEqual(f.variable, self.v1)
        self.assertEqual(f.device, self.pd1)
        self.assertEqual(f.input_stream, self.s1)
        self.assertEqual(f.name, "test")
        elements = self.s1.slug.split('--')
        filter_stream_key = '--'.join(['f', ] + elements[1:])
        self.assertEqual(f.slug, filter_stream_key)
        self.assertTrue(f.active)

        self.assertEqual(State.objects.filter(filter=f).count(), 3)
        self.assertEqual(State.objects.filter(filter=f, label="Green").count(), 1)
        self.assertEqual(State.objects.filter(filter=f, label="Red").count(), 1)
        self.assertEqual(State.objects.filter(filter=f, label="Blue").count(), 1)

        # test duplicate filter for device
        payload = {
            "name": "test",
            "variable": self.v1.id,
            "device": self.pd1.id,
            "states": "Green, Red, Blue",
            "submit": "Submit"
        }
        self.assertEqual(StreamFilter.objects.all().count(), 2)
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(StreamFilter.objects.all().count(), 2)
        self.assertFormError(resp, 'form', None, "Filter for this stream already exists")

    def testStreamFilterDeleteView(self):
        f1 = StreamFilter.objects.create_filter_from_streamid(name='filter 1',
                                                              input_stream=self.s1,
                                                              created_by=self.u2)
        extra_payload = {
            "notification_recipient": "admin",
            "notification_level": "warn",
            "custom_note": "dummy"
        }
        state11 = State.objects.create(label="state11", filter=f1, created_by=self.u2)
        state21 = State.objects.create(label="state21", filter=f1, created_by=self.u2)
        StreamFilterAction.objects.create(
            type='eml', created_by=self.u2, extra_payload=extra_payload, state=state11, on='exit'
        )
        StreamFilterAction.objects.create(
            type='eml', created_by=self.u2, extra_payload=extra_payload, state=state21, on='entry'
        )
        transition1 = StateTransition.objects.create(src=state11, dst=state21, filter=f1, created_by=self.u2)
        StreamFilterTrigger.objects.create(operator='ge', created_by=self.u2, filter=f1, threshold=10, transition=transition1)

        url = reverse('filter:delete', kwargs={"slug": f1.slug})

        self.client.login(email='user1@foo.com', password='pass')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertEqual(StreamFilter.objects.all().count(), 1)
        self.assertEqual(StateTransition.objects.all().count(), 1)
        self.assertEqual(StreamFilterAction.objects.all().count(), 2)
        self.assertEqual(State.objects.all().count(), 2)
        self.assertEqual(StreamFilterTrigger.objects.all().count(), 1)
        self.assertEqual(self.s1.stream_filter, f1)

        resp = self.client.post(url, data={"submit": "Confirm delete"})
        self.assertRedirects(resp, expected_url=reverse('org:project:detail', kwargs={"org_slug": self.p1.org.slug, "pk": str(self.p1.id)}), status_code=302, target_status_code=200)

        self.assertEqual(StreamFilter.objects.all().count(), 0)
        self.assertEqual(StateTransition.objects.all().count(), 0)
        self.assertEqual(StreamFilterAction.objects.all().count(), 0)
        self.assertEqual(State.objects.all().count(), 0)
        self.assertEqual(StreamFilterTrigger.objects.all().count(), 0)

    def testStateCreateView(self):
        f1 = StreamFilter.objects.create_filter_from_streamid(name='filter 1',
                                                              input_stream=self.s1,
                                                              created_by=self.u2)

        url = reverse('filter:state-create', kwargs={"slug": f1.slug})

        self.client.login(email='user1@foo.com', password='pass')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertEqual(StreamFilter.objects.all().count(), 1)
        self.assertEqual(f1.states.all().count(), 0)
        self.assertEqual(State.objects.all().count(), 0)
        self.assertEqual(self.s1.stream_filter, f1)

        resp = self.client.post(url, data={'label': 'Green', 'submit': 'Submit'})
        self.assertRedirects(resp, expected_url=reverse("filter:state-detail", kwargs={"filter_slug": f1.slug, "slug": "green"}), status_code=302, target_status_code=200)

        self.assertEqual(StreamFilter.objects.all().count(), 1)
        self.assertEqual(State.objects.all().count(), 1)
        self.assertEqual(f1.states.all().count(), 1)
        self.assertEqual(f1.states.all()[0].label, "Green")

    def testStateDeleteView(self):
        f1 = StreamFilter.objects.create_filter_from_streamid(name='filter 1',
                                                              input_stream=self.s1,
                                                              created_by=self.u2)
        extra_payload = {
            "notification_recipient": "admin",
            "notification_level": "warn",
            "custom_note": "dummy"
        }
        state11 = State.objects.create(label="state11", filter=f1, created_by=self.u2)
        state21 = State.objects.create(label="state21", filter=f1, created_by=self.u2)
        StreamFilterAction.objects.create(
            type='eml', created_by=self.u2, extra_payload=extra_payload, state=state11, on='exit'
        )
        StreamFilterAction.objects.create(
            type='eml', created_by=self.u2, extra_payload=extra_payload, state=state21, on='entry'
        )

        url = reverse('filter:state-delete', kwargs={"filter_slug": f1.slug, "slug": state11.slug})

        self.client.login(email='user1@foo.com', password='pass')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertEqual(StreamFilter.objects.all().count(), 1)
        self.assertEqual(State.objects.all().count(), 2)
        self.assertEqual(f1.states.all().count(), 2)
        self.assertEqual(StreamFilterAction.objects.all().count(), 2)
        self.assertEqual(self.s1.stream_filter, f1)

        resp = self.client.post(url, data={"submit": "Confirm delete"})
        self.assertRedirects(resp, expected_url=reverse("filter:detail", kwargs={'slug': f1.slug}),
                             status_code=302,
                             target_status_code=200)

        self.assertEqual(StreamFilter.objects.all().count(), 1)
        self.assertEqual(State.objects.all().count(), 1)
        self.assertEqual(f1.states.all().count(), 1)
        self.assertEqual(StreamFilterAction.objects.all().count(), 1)
        self.assertEqual(f1.states.all()[0].label, "state21")

    def testTransitionForStreamCreateView(self):
        f1 = StreamFilter.objects.create_filter_from_streamid(name='filter 1',
                                                              input_stream=self.s1,
                                                              created_by=self.u2)
        extra_payload = {
            "notification_recipient": "admin",
            "notification_level": "warn",
            "custom_note": "dummy"
        }
        state11 = State.objects.create(label="state11", filter=f1, created_by=self.u2)
        state21 = State.objects.create(label="state21", filter=f1, created_by=self.u2)
        a1 = StreamFilterAction.objects.create(
            type='eml', created_by=self.u2, extra_payload=extra_payload, on='exit', state=state11
        )
        a2 = StreamFilterAction.objects.create(
            type='eml', created_by=self.u2, extra_payload=extra_payload, on='entry', state=state21
        )

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
            o=100.0,
            created_by=self.u2
        )
        self.s1.output_unit = output_unit1
        self.s1.save()
        url = reverse('filter:transition-create', kwargs={"slug": f1.slug})

        self.client.login(email='user1@foo.com', password='pass')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertEqual(StreamFilter.objects.all().count(), 1)
        self.assertEqual(f1.states.all().count(), 2)
        self.assertEqual(f1.transitions.all().count(), 0)
        self.assertEqual(StreamFilterTrigger.objects.all().count(), 0)
        self.assertEqual(self.s1.stream_filter, f1)

        resp = self.client.post(url, data={'src': state11.id, 'dst': state21.id, 'operator': 'ge', 'threshold': 10, 'submit': 'Submit'}, follow=True)
        self.assertRedirects(resp, expected_url=reverse("filter:detail", kwargs={'slug': f1.slug}),
                             status_code=302,
                             target_status_code=200)

        self.assertEqual(StreamFilter.objects.all().count(), 1)
        self.assertEqual(f1.states.all().count(), 2)
        self.assertEqual(f1.transitions.all().count(), 1)
        self.assertEqual(StreamFilterTrigger.objects.all().count(), 1)
        self.assertEqual(self.s1.stream_filter, f1)
        transition = StateTransition.objects.all().first()
        self.assertEqual(transition.src, state11)
        self.assertEqual(transition.dst, state21)
        self.assertEqual(transition.triggers.all().count(), 1)
        trigger = transition.triggers.all()[0]
        self.assertEqual(trigger.user_threshold, 10)
        self.assertEqual(trigger.user_output_unit, output_unit1)
        self.assertEqual(trigger.threshold, -180)

    def testTransitionForProjectCreateView(self):
        f1 = StreamFilter.objects.create_filter_from_project_and_variable(name='filter 1',
                                                                          proj=self.s1.project,
                                                                          var=self.s1.variable,
                                                                          created_by=self.u2)
        extra_payload = {
            "notification_recipient": "admin",
            "notification_level": "warn",
            "custom_note": "dummy"
        }
        state11 = State.objects.create(label="state11", filter=f1, created_by=self.u2)
        state21 = State.objects.create(label="state21", filter=f1, created_by=self.u2)

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
            o=100.0,
            created_by=self.u2
        )
        self.s1.variable.output_unit = output_unit1
        self.s1.variable.save()
        url = reverse('filter:transition-create', kwargs={"slug": f1.slug})

        self.client.login(email='user1@foo.com', password='pass')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertEqual(StreamFilter.objects.all().count(), 1)
        self.assertEqual(f1.states.all().count(), 2)
        self.assertEqual(f1.transitions.all().count(), 0)
        self.assertEqual(StreamFilterTrigger.objects.all().count(), 0)

        resp = self.client.post(url, data={'src': state11.id, 'dst': state21.id, 'operator': 'ge', 'threshold': 10, 'submit': 'Submit'}, follow=True)
        self.assertRedirects(resp, expected_url=reverse("filter:detail", kwargs={'slug': f1.slug}),
                             status_code=302,
                             target_status_code=200)

        self.assertEqual(StreamFilter.objects.all().count(), 1)
        transition = StateTransition.objects.all().first()
        self.assertEqual(transition.triggers.all().count(), 1)
        trigger = transition.triggers.all()[0]
        self.assertEqual(trigger.user_threshold, 10)
        self.assertEqual(trigger.user_output_unit, output_unit1)
        self.assertEqual(trigger.threshold, -180)

    def testTransitionDeleteView(self):
        f1 = StreamFilter.objects.create_filter_from_streamid(name='filter 1',
                                                              input_stream=self.s1,
                                                              created_by=self.u2)
        extra_payload = {
            "notification_recipient": "admin",
            "notification_level": "warn",
            "custom_note": "dummy"
        }
        state11 = State.objects.create(label="state11", filter=f1, created_by=self.u2)
        state21 = State.objects.create(label="state21", filter=f1, created_by=self.u2)
        a1 = StreamFilterAction.objects.create(
            type='eml', created_by=self.u2, extra_payload=extra_payload, on='exit', state=state11
        )
        a2 = StreamFilterAction.objects.create(
            type='eml', created_by=self.u2, extra_payload=extra_payload, on='entry', state=state21
        )
        transition1 = StateTransition.objects.create(src=state11, dst=state21, filter=f1, created_by=self.u2)
        t1 = StreamFilterTrigger.objects.create(operator='ge', created_by=self.u2, filter=f1, threshold=10, transition=transition1)

        url = reverse('filter:transition-delete', kwargs={"filter_slug": f1.slug, "pk": transition1.pk})

        self.client.login(email='user1@foo.com', password='pass')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertEqual(StreamFilter.objects.all().count(), 1)
        self.assertEqual(f1.states.all().count(), 2)
        self.assertEqual(f1.transitions.all().count(), 1)
        self.assertEqual(StreamFilterTrigger.objects.all().count(), 1)
        self.assertEqual(StreamFilterAction.objects.all().count(), 2)
        self.assertEqual(self.s1.stream_filter, f1)

        resp = self.client.post(url, data={"submit": "Confirm delete"})
        self.assertRedirects(resp, expected_url=reverse("filter:detail", kwargs={'slug': f1.slug}),
                             status_code=302,
                             target_status_code=200)

        self.assertEqual(StreamFilter.objects.all().count(), 1)
        self.assertEqual(f1.states.all().count(), 2)
        self.assertEqual(f1.transitions.all().count(), 0)
        self.assertEqual(StreamFilterTrigger.objects.all().count(), 0)
        self.assertEqual(StreamFilterAction.objects.all().count(), 2)

    def testTriggerAddForStreamView(self):
        f1 = StreamFilter.objects.create_filter_from_streamid(name='filter 1',
                                                              input_stream=self.s1,
                                                              created_by=self.u2)
        extra_payload = {
            "notification_recipient": "admin",
            "notification_level": "warn",
            "custom_note": "dummy"
        }
        state11 = State.objects.create(label="state11", filter=f1, created_by=self.u2)
        state21 = State.objects.create(label="state21", filter=f1, created_by=self.u2)
        a1 = StreamFilterAction.objects.create(
            type='eml', created_by=self.u2, extra_payload=extra_payload, on='exit', state=state11
        )
        a2 = StreamFilterAction.objects.create(
            type='eml', created_by=self.u2, extra_payload=extra_payload, on='entry', state=state21
        )
        transition1 = StateTransition.objects.create(src=state11, dst=state21, filter=f1, created_by=self.u2)
        t1 = StreamFilterTrigger.objects.create(
            operator='ge', created_by=self.u2, filter=f1, threshold=10, transition=transition1
        )

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

        url = reverse('filter:trigger-add', kwargs={"filter_slug": f1.slug, "pk": transition1.pk})

        self.client.login(email='user1@foo.com', password='pass')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertEqual(StreamFilter.objects.all().count(), 1)
        self.assertEqual(StateTransition.objects.all().count(), 1)
        self.assertEqual(StreamFilterAction.objects.all().count(), 2)
        self.assertEqual(State.objects.all().count(), 2)
        self.assertEqual(StreamFilterTrigger.objects.all().count(), 1)
        self.assertEqual(self.s1.stream_filter, f1)

        resp = self.client.post(url, data={"operator": "ge", "user_threshold": 10})
        self.assertRedirects(resp, expected_url=reverse("filter:detail", kwargs={'slug': f1.slug}), status_code=302, target_status_code=200)

        self.assertEqual(StreamFilter.objects.all().count(), 1)
        self.assertEqual(StateTransition.objects.all().count(), 1)
        self.assertEqual(StreamFilterAction.objects.all().count(), 2)
        self.assertEqual(State.objects.all().count(), 2)
        self.assertEqual(StreamFilterTrigger.objects.all().count(), 2)
        self.assertEqual(transition1.triggers.all().count(), 2)

        trigger = transition1.triggers.all().last()
        self.assertEqual(trigger.user_threshold, 10)
        output_mdo = get_stream_output_mdo(self.s1)
        self.assertEqual(trigger.user_output_unit, output_unit1)
        self.assertEqual(trigger.threshold, output_mdo.compute_reverse(10))

    def testTriggerAddForProjectView(self):
        f1 = StreamFilter.objects.create_filter_from_project_and_variable(name='filter 1',
                                                                          proj=self.s1.project,
                                                                          var=self.s1.variable,
                                                                          created_by=self.u2)
        extra_payload = {
            "notification_recipient": "admin",
            "notification_level": "warn",
            "custom_note": "dummy"
        }
        state11 = State.objects.create(label="state11", filter=f1, created_by=self.u2)
        state21 = State.objects.create(label="state21", filter=f1, created_by=self.u2)
        transition1 = StateTransition.objects.create(src=state11, dst=state21, filter=f1, created_by=self.u2)
        t1 = StreamFilterTrigger.objects.create(operator='ge', created_by=self.u2, filter=f1, threshold=10, transition=transition1)

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
            o=-50.0,
            created_by=self.u2
        )
        self.s1.variable.output_unit = output_unit1
        self.s1.variable.save()

        url = reverse('filter:trigger-add', kwargs={"filter_slug": f1.slug, "pk": transition1.pk})

        self.client.login(email='user1@foo.com', password='pass')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.post(url, data={"operator": "ge", "user_threshold": 10})
        self.assertRedirects(resp, expected_url=reverse("filter:detail", kwargs={'slug': f1.slug}), status_code=302, target_status_code=200)

        trigger = transition1.triggers.all().last()
        self.assertEqual(trigger.user_threshold, 10)
        self.assertEqual(trigger.user_output_unit, output_unit1)
        self.assertEqual(trigger.threshold, 120)



