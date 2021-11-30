from django.test import TestCase

from apps.datablock.models import DataBlock
from apps.fleet.models import Fleet
from apps.physicaldevice.models import Device
from apps.stream.models import StreamId, StreamVariable

from ..test_util import TestMixin
from .utils import *
from .utils import _get_real_slug


class ObjectBySlugTests(TestMixin, TestCase):

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

    def tearDown(self):
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        DataBlock.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testRealSlug(self):
        real = _get_real_slug('@foo')
        self.assertEqual(real, 'foo')
        real = _get_real_slug('^bar')
        self.assertEqual(real, 'bar')
        real = _get_real_slug('d--0001')
        self.assertEqual(real, 'd--0001')

    def testProject(self):
        n, o = get_object_by_slug(self.p1.obj_target_slug)
        self.assertEqual(n, 'project')
        self.assertIsNotNone(o)
        self.assertEqual(o.id, self.p1.id)

    def testDevice(self):
        n, o = get_object_by_slug(self.pd1.obj_target_slug)
        self.assertEqual(n, 'device')
        self.assertIsNotNone(o)
        self.assertEqual(o.id, self.pd1.id)

    def testVariable(self):
        n, o = get_object_by_slug(self.v1.obj_target_slug)
        self.assertEqual(n, 'variable')
        self.assertIsNotNone(o)
        self.assertEqual(o.id, self.v1.id)

    def testStream(self):
        StreamId.objects.create_after_new_device(self.pd1)
        StreamId.objects.create_after_new_device(self.pd2)
        s1 = StreamId.objects.filter(variable=self.v1).first()

        n, o = get_object_by_slug(s1.obj_target_slug)
        self.assertEqual(n, 'stream')
        self.assertIsNotNone(o)
        self.assertEqual(o.id, s1.id)

    def testStreamWithoutStreamId(self):
        sys_stream = '--'.join(['s', self.pd2.project.formatted_gid, self.pd2.formatted_gid, '5800'])

        n, o = get_object_by_slug(sys_stream)
        self.assertEqual(n, 'stream')
        self.assertIsNone(o)

    def testDataBlock(self):
        db1 = DataBlock.objects.create(org=self.o1, title='test1', device=self.pd1, block=1, created_by=self.u1)
        DataBlock.objects.create(org=self.o1, title='test2', device=self.pd1, block=2, created_by=self.u1)

        n, o = get_object_by_slug(db1.obj_target_slug)
        self.assertEqual(n, 'datablock')
        self.assertIsNotNone(o)
        self.assertEqual(o.id, db1.id)

    def testDeviceOrDataBlock(self):
        db1 = DataBlock.objects.create(org=self.o1, title='test1', device=self.pd1, block=1, created_by=self.u1)
        DataBlock.objects.create(org=self.o1, title='test2', device=self.pd1, block=2, created_by=self.u1)

        b = get_device_or_block('b--0001-123-0000-0001')
        self.assertIsNone(b)

        b = get_device_or_block(db1.obj_target_slug)
        self.assertIsNotNone(b)
        self.assertEqual(b.title, db1.title)

        d = get_device_or_block('d--0000-123-0000-0001')
        self.assertIsNone(d)

        d = get_device_or_block(self.pd1.obj_target_slug)
        self.assertIsNotNone(d)
        self.assertEqual(d.id, self.pd1.id)

    def testFleet(self):
        fleet1 = Fleet.objects.create(name='F1', org=self.o2, created_by=self.u2)
        n, o = get_object_by_slug(fleet1.obj_target_slug)
        self.assertEqual(n, 'fleet')
        self.assertIsNotNone(o)
        self.assertEqual(o.id, fleet1.id)

    def testUser(self):
        n, o = get_object_by_slug(self.u2.obj_target_slug)
        self.assertEqual(n, 'user')
        self.assertIsNotNone(o)
        self.assertEqual(o.id, self.u2.id)

    def testOrg(self):
        n, o = get_object_by_slug(self.o2.obj_target_slug)
        self.assertEqual(n, 'org')
        self.assertIsNotNone(o)
        self.assertEqual(o.id, self.o2.id)

    def testErorrHandleGetObjectWithDuplicate(self):
        # While there should not be duplicated slugs
        # test that if they exist, they don't crash the get_object_by_slug function
        s1 = StreamId.objects.create_stream(
            project=self.pd1.project, variable=self.v1, device=self.pd1, created_by=self.u2
        )
        s2 = StreamId.objects.create_stream(
            project=self.pd1.project, variable=self.v1, device=self.pd1, created_by=self.u2
        )
        self.assertEqual(s1.slug, s2.slug)
        n, o = get_object_by_slug(s2.slug)
        self.assertEqual(n, 'stream')
        self.assertIsNotNone(o)
        self.assertTrue(str(o.id) in [str(s1.id), str(s2.id)])
