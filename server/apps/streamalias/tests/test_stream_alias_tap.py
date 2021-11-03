from django.utils import timezone
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.utils.test_util import TestMixin
from apps.stream.models import StreamId, StreamVariable
from apps.physicaldevice.models import Device

from ..models import *

user_model = get_user_model()


class StreamAliasTapTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.p1.project_template = self.pt1
        self.p1.save()
        self.p2.project_template = self.pt1
        self.p2.save()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=1,
        )
        self.v2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p2, created_by=self.u3, lid=2,
        )
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)

    def tearDown(self):
        StreamAliasTap.objects.all().delete()
        StreamAlias.objects.all().delete()
        self.projectTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()
    
    def testBasicStreamAliasTapObject(self):
        sa1 = StreamAlias.objects.create(
            name='some alias',
            org=self.o2,
            created_by=self.u2,
        )
        s1 = StreamId.objects.create_stream(
            project=self.p1,
            variable=self.v1,
            device=self.pd1,
            created_by=self.u2
        )
        sat1 = StreamAliasTap.objects.create(
            alias=sa1,
            timestamp=timezone.now(),
            stream=s1,
            created_by=self.u2,
        )
        self.assertEqual(sat1.alias, sa1)
        self.assertTrue('Stream Alias Tap ' in str(sat1))
        
        s2 = StreamId.objects.create_stream(
            project=self.p1,
            variable=self.v1,
            device=self.pd1,
            created_by=self.u2
        )
        sat2 = StreamAliasTap.objects.create(
            alias=sa1,
            timestamp=timezone.now(),
            stream=s2,
            created_by=self.u2,
        )
        self.assertEqual(sa1.taps.count(), 2)

        # Test that alias tap is deleted after stream is deleted
        s1.delete()
        self.assertEqual(StreamAliasTap.objects.count(), 1)
        self.assertEqual(StreamAliasTap.objects.filter(stream=s1).count(), 0)

        # Test that alias tap is deleted after alias is deleted
        sa1.delete()
        self.assertEqual(StreamAliasTap.objects.count(), 0)

    def testHasAccess(self):
        sa0 = StreamAlias.objects.create(
            name='some alias',
            org=self.o2,
            created_by=self.u1,
        )
        s0 = StreamId.objects.create_stream(
            project=self.p1,
            variable=self.v1,
            device=self.pd1,
            created_by=self.u2
        )
        sat0 = StreamAliasTap.objects.create(
            alias=sa0,
            timestamp=timezone.now(),
            stream=s0,
            created_by=self.u2,
        )
        sa1 = StreamAlias.objects.create(
            name='some other alias',
            org=self.o2,
            created_by=self.u2,
        )
        sat1 = StreamAliasTap.objects.create(
            alias=sa1,
            timestamp=timezone.now(),
            stream=s0,
            created_by=self.u1,
        )
        sa2 = StreamAlias.objects.create(
            name='yet another alias',
            org=self.o3,
            created_by=self.u1,
        )
        sat2 = StreamAliasTap.objects.create(
            alias=sa2,
            timestamp=timezone.now(),
            stream=s0,
            created_by=self.u1,
        )
        self.assertTrue(sat0.has_access(self.u1))
        self.assertTrue(sat0.has_access(self.u2))
        self.assertFalse(sat0.has_access(self.u3))
        self.assertTrue(sat1.has_access(self.u1))
        self.assertTrue(sat1.has_access(self.u2))
        self.assertFalse(sat1.has_access(self.u3))
        self.assertTrue(sat2.has_access(self.u1))
        self.assertFalse(sat2.has_access(self.u2))
        self.assertTrue(sat2.has_access(self.u3))
