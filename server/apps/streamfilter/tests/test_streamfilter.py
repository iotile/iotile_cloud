from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.physicaldevice.models import Device
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.models import StreamData
from apps.streamdata.utils import get_stream_output_mdo
from apps.utils.test_util import TestMixin
from apps.vartype.models import VarType, VarTypeOutputUnit

from ..cache_utils import *
from ..models import *
from ..serializers import *

user_model = get_user_model()


class StreamFilterTestCase(TestMixin, TestCase):
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
        State.objects.all().defer()
        StreamFilter.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasicFilterObject(self):
        f = StreamFilter.objects.create_filter_from_streamid(name='Filter 1',
                                                             input_stream=self.s1, created_by=self.u2)
        self.assertEqual(f.slug.split('--')[0], 'f')
        self.assertEqual(f.slug.split('--')[1:], self.s1.slug.split('--')[1:])
        self.assertEqual(f.project, self.s1.project)

    def testBasicCreateFunctions(self):
        f = StreamFilter.objects.create_filter_from_streamid(name='Filter 1',
                                                             input_stream=self.s1, created_by=self.u2)
        self.assertEqual(f.slug.split('--')[0], 'f')
        self.assertEqual(f.slug.split('--')[1:], self.s1.slug.split('--')[1:])
        self.assertEqual(f.project, self.s1.project)

        self.assertEqual(self.v2.project, self.pd2.project)
        s = StreamId.objects.create_stream(
            project=self.pd2.project, variable=self.v2, device=self.pd2, created_by=self.u3
        )
        f = StreamFilter.objects.create_filter_from_device_and_variable(name='Filter 2',
                                                                        var=self.v2,
                                                                        dev=self.pd2,
                                                                        created_by=self.u2)
        self.assertIsNotNone(f)
        self.assertEqual(f.slug.split('--')[0], 'f')
        self.assertEqual(f.slug.split('--')[1], self.p2.formatted_gid)
        self.assertEqual(f.slug.split('--')[2], self.pd2.formatted_gid)
        self.assertEqual(f.slug.split('--')[3], self.v2.formatted_lid)
        self.assertEqual(f.project, self.pd2.project)
        self.assertEqual(f.input_stream, s)
        self.assertEqual(f.input_stream.project, self.pd2.project)
        self.assertEqual(f.input_stream.device, self.pd2)
        self.assertEqual(f.input_stream.variable, self.v2)

        v = StreamVariable.objects.create_variable(
            name='Var C', project=self.p1, created_by=self.u2, lid=3,
        )
        f = StreamFilter.objects.create_filter_from_project_and_variable(name='Filter 2',
                                                                        var=v,
                                                                        proj=self.p1,
                                                                        created_by=self.u2)
        self.assertIsNotNone(f)
        self.assertEqual(f.slug, 'f--{0}----0003'.format(self.p1.formatted_gid))
        self.assertEqual(f.slug.split('--')[1], self.p1.formatted_gid)
        self.assertEqual(f.slug.split('--')[3], v.formatted_lid)

    def testHasAccess(self):
        f1 = StreamFilter.objects.create_filter_from_streamid(name='Filter 1',
                                                              input_stream=self.s1, created_by=self.u2)
        f2 = StreamFilter.objects.create_filter_from_streamid(name='Filter 2',
                                                              input_stream=self.s2, created_by=self.u2)
        self.assertTrue(f1.has_access(self.u1))
        self.assertTrue(f1.has_access(self.u2))
        self.assertFalse(f1.has_access(self.u3))
        self.assertTrue(f2.has_access(self.u1))
        self.assertFalse(f2.has_access(self.u2))
        self.assertTrue(f2.has_access(self.u3))
        self.o2.register_user(self.u3)
        self.assertTrue(self.o2.is_member(self.u3))
        self.assertTrue(self.o2.has_access(self.u3))
        self.assertTrue(f1.has_access(self.u3))
        self.assertTrue(f1.has_access(self.u3))

    def testCachedSerializerPriority(self):
        var = StreamVariable.objects.create_variable(
            name='Var', project=self.p1, created_by=self.u2, lid=10,
        )
        pd1 = Device.objects.create_device(
            project=self.p1, label='d10', template=self.dt1, created_by=self.u2
        )
        pd2 = Device.objects.create_device(
            project=self.p1, label='d20', template=self.dt1, created_by=self.u2
        )
        s1 = StreamId.objects.create_stream(
            project=self.p1, variable=var, device=pd1, created_by=self.u2
        )
        s2 = StreamId.objects.create_stream(
            project=self.p1, variable=var, device=pd2, created_by=self.u2
        )
        s_filter = StreamFilter.objects.create_filter_from_streamid(name='Filter s1',
                                                                    input_stream=s1,
                                                                    created_by=self.u2)
        key = '--'.join(['f',] + s1.slug.split('--')[1:])
        self.assertEqual(s_filter.slug, key)
        p_filter = StreamFilter.objects.create_filter_from_project_and_variable(name='Project Filter',
                                                                                proj=s2.project,
                                                                                var=s2.variable,
                                                                                created_by=self.u2)

        s1_data = cached_serialized_filter_for_slug(slug=s1.slug)
        self.assertEqual(s1_data['slug'], s_filter.slug)
        s1_data = cached_serialized_filter_for_slug(slug=s1.slug)
        self.assertEqual(s1_data['slug'], s_filter.slug)

        s2_data = cached_serialized_filter_for_slug(slug=s2.slug)
        self.assertEqual(s2_data['slug'], p_filter.slug)
        s2_data = cached_serialized_filter_for_slug(slug=s2.slug)
        self.assertEqual(s2_data['slug'], p_filter.slug)

        s3_data = cached_serialized_filter_for_slug(slug='s--0000-0001--0000-0000-0000-0005--1111')
        self.assertEqual(s3_data,{'empty': True})
        s3_data = cached_serialized_filter_for_slug(slug='s--0000-0001--0000-0000-0000-0005--1111')
        self.assertEqual(s3_data,{'empty': True})

    def testFilterSerializer(self):
        f = StreamFilter.objects.create_filter_from_streamid(
            name='Filter 1', input_stream=self.s1, created_by=self.u2
        )
        extra_payload = {
            "notification_recipient": "admin",
            "notification_level": "warn",
            "custom_note": "dummy"
        }
        state1 = State.objects.create(label="state1", filter=f, created_by=self.u2)
        state2 = State.objects.create(label="state2", filter=f, created_by=self.u2)
        a1 = StreamFilterAction.objects.create(
            type='eml', created_by=self.u2, extra_payload=extra_payload, on='exit', state=state1
        )
        a2 = StreamFilterAction.objects.create(
            type='eml', created_by=self.u2, extra_payload=extra_payload, on='entry', state=state2
        )
        transition1 = StateTransition.objects.create(src=state1, dst=state2, filter=f, created_by=self.u2)
        trigger1 = StreamFilterTrigger.objects.create(
            operator='ge', created_by=self.u2, filter=f, threshold=10, transition=transition1
        )

        filter = cached_serialized_filter_for_slug(self.s1.slug)
        self.assertEqual(filter['slug'], f.slug)
        self.assertEqual(filter['name'], 'Filter 1')
        self.assertEqual(filter['input_stream'], self.s1.slug)
        self.assertEqual(filter['project'], self.s1.project.slug)
        self.assertEqual(filter['device'], self.s1.device.slug)
        self.assertEqual(filter['variable'], self.s1.variable.slug)

        states = filter['states']
        self.assertEqual(len(states), 2)
        self.assertEqual(states[0]['slug'], 'state1')
        self.assertEqual(states[1]['slug'], 'state2')
        self.assertEqual(len(states[0]['actions']), 1)
        self.assertEqual(states[0]['actions'][0]['type'], 'eml')
        self.assertEqual(states[0]['actions'][0]['extra_payload']['custom_note'], 'dummy')

        transitions = filter['transitions']
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0]['src'], state1.id)
        self.assertEqual(transitions[0]['dst'], state2.id)

        triggers = transitions[0]['triggers']
        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0]['operator'], trigger1.operator)
        self.assertEqual(triggers[0]['threshold'], 10.0)
