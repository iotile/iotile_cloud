from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()


class StreamAliasTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.projectTestSetup()

    def tearDown(self):
        StreamAlias.objects.all().delete()
        self.projectTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testStreamAliasId(self):
        self.assertEqual(formatted_alias_id(int64gid(1)),
                         'a--0000-0000-0000-0001')
        self.assertEqual(formatted_alias_id(int64gid(42)),
                         'a--0000-0000-0000-002a')
        self.assertEqual(formatted_alias_id(int64gid(300000)),
                         'a--0000-0000-0004-93e0')
    
    def testBasicStreamAliasObject(self):
        sa1 = StreamAlias.objects.create(
            name='some alias',
            org=self.o2,
            created_by=self.u2,
        )
        expected = '0000-0000-0000-0001'
        self.assertEqual(sa1.formatted_gid, expected)
        slug_expected = 'a--{}'.format(expected)
        self.assertEqual(sa1.slug, slug_expected)
        self.assertEqual(str(sa1), '{} - some alias'.format(slug_expected))

        # Test that alias is deleted after org is deleted
        self.o2.delete()
        self.assertEqual(StreamAlias.objects.count(), 0)

    def testHasAccess(self):
        sa0 = StreamAlias.objects.create(
            name='some alias',
            org=self.o2,
            created_by=self.u1,
        )
        sa1 = StreamAlias.objects.create(
            name='some other alias',
            org=self.o2,
            created_by=self.u2,
        )
        sa2 = StreamAlias.objects.create(
            name='yet another alias',
            org=self.o3,
            created_by=self.u1,
        )
        self.assertTrue(sa0.has_access(self.u1))
        self.assertTrue(sa0.has_access(self.u2))
        self.assertFalse(sa0.has_access(self.u3))
        self.assertTrue(sa1.has_access(self.u1))
        self.assertTrue(sa1.has_access(self.u2))
        self.assertFalse(sa1.has_access(self.u3))
        self.assertTrue(sa2.has_access(self.u1))
        self.assertFalse(sa2.has_access(self.u2))
        self.assertTrue(sa2.has_access(self.u3))
