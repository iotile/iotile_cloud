import json
from django.test import SimpleTestCase
from django.test import TestCase

from apps.utils.test_util import TestMixin

from ..models import *
from ..roles import *

user_model = get_user_model()


class OrgTestCase(SimpleTestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_role_complation(self):

        permission_set = set()
        for permission in ORG_PERMISSIONS:
            permission_set.add(permission)

            self.assertTrue(permission in ORG_ROLE_DESCRIPTIONS, 'Description {} not set'.format(permission))

        for key in ORG_ROLE_DESCRIPTIONS.keys():
            self.assertTrue(key in permission_set, '{} permission should be removed from description'.format(key))
            for dkey in ['label', 'description', 'hidden']:
                self.assertTrue(dkey in ORG_ROLE_DESCRIPTIONS[key],
                                'Description for {} missing {}'.format(key, dkey))

        # Every role should have a permission set
        for role in ORG_ROLE_CHOICES:
            self.assertTrue(role[0] in ORG_ROLE_PERMISSIONS)

            # Every role should have a value for every permission
            for permission in ORG_PERMISSIONS:
                self.assertTrue(permission in ORG_ROLE_PERMISSIONS[role[0]],
                                'Permission {} not set on role {}'.format(permission, role[0]))

            # Ensure we don't have any extra garbage
            for key in ORG_ROLE_PERMISSIONS[role[0]].keys():
                self.assertTrue(key in permission_set,
                                '{} permission should be removed on role {}'.format(key, role[0]))


class OrgPermissionsTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        return

    def tearDown(self):
        self.projectTestTearDown()
        Org.objects.all().delete()
        OrgMembership.objects.all().delete()
        self.userTestTearDown()

    def testDefaultPermisssion(self):
        o1 = Org.objects.create_org(name='My Org 2', created_by=self.u2)
        membership = OrgMembership(user=self.u3, org=o1, is_org_admin=True)
        membership.save()
        self.assertFalse(type(membership.permissions) is None)
        self.assertTrue(type(membership.permissions) is dict)
        self.assertFalse(membership.permissions['can_delete_org'])
        self.assertFalse(membership.permissions['can_manage_users'])
        self.assertFalse(membership.permissions['can_manage_org_and_projects'])
        self.assertFalse(membership.permissions['can_claim_devices'])
        self.assertFalse(membership.permissions['can_create_stream_ids'])
        self.assertFalse(membership.permissions['can_access_classic'])

    def testObjectPermissions(self):
        u4 = self.create_user('user4', 'user4@foo.com')
        u5 = self.create_user('user5', 'user5@foo.com')
        u6 = self.create_user('user6', 'user6@foo.com')
        o1 = Org.objects.create_org(name='My Org 2', created_by=self.u2)
        o1.register_user(u4, role='a1')
        o1.register_user(u5, role='m1')
        o1.register_user(u6, role='r1')

        self.assertTrue(o1.has_permission(self.u2, 'can_delete_org'))
        self.assertFalse(o1.has_permission(u4, 'can_delete_org'))
        self.assertFalse(o1.has_permission(u5, 'can_delete_org'))
        self.assertFalse(o1.has_permission(u6, 'can_delete_org'))

        self.assertTrue(o1.has_permission(u4, 'can_manage_users'))
        self.assertFalse(o1.has_permission(u5, 'can_manage_users'))
        self.assertFalse(o1.has_permission(u6, 'can_manage_users'))
        self.assertTrue(o1.has_permission(u4, 'can_claim_devices'))
        self.assertFalse(o1.has_permission(u5, 'can_claim_devices'))
        self.assertFalse(o1.has_permission(u6, 'can_claim_devices'))
