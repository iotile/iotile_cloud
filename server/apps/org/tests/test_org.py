from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.utils.test_util import TestMixin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from ..models import Org, OrgMembership, OrgDomain
from ..roles import ORG_ROLE_PERMISSIONS

user_model = get_user_model()


class OrgTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        return

    def tearDown(self):
        self.projectTestTearDown()
        Org.objects.all().delete()
        OrgMembership.objects.all().delete()
        OrgDomain.objects.all().delete()
        self.userTestTearDown()

    def testBasicOrgObject(self):
        o1 = Org.objects.create(name='My Org', created_by=self.u2)
        self.assertEqual(o1.slug, 'my-org')
        self.assertEqual(o1.get_absolute_url(), '/org/my-org/')

    def testObjectAccess(self):
        self.assertEqual(OrgMembership.objects.count(), 0)
        o2 = Org.objects.create(name='My Org 2', created_by=self.u2)

        # Non member has no access
        self.assertFalse(o2.has_access(self.u2))
        o2.register_user(self.u2)
        self.assertTrue(o2.has_access(self.u2))

        self.assertFalse(o2.has_access(self.u3))

        # Staff user have access
        self.assertTrue(self.u1.is_staff)
        self.assertTrue(o2.has_access(self.u1))
        # Except when inactive
        self.u1.is_staff = False
        self.u1.save()
        self.assertFalse(o2.has_access(self.u1))

        # Inactive user doesn't have access
        o3 = Org.objects.create(name='My Org 3', created_by=self.u3)
        o3.register_user(self.u3)
        self.assertTrue(o3.has_access(self.u3))
        self.u3.is_active = False
        self.u3.save()
        self.assertFalse(o2.has_access(self.u3))

    def testInactiveMembership(self):
        Org.objects.create_org(name='My Org 2', created_by=self.u2)
        o2 = Org.objects.create_org(name='My Org 3', created_by=self.u3)
        o3 = Org.objects.create_org(name='My Org 4', created_by=self.u2)
        self.assertEqual(Org.objects.members_count(o3), 1)
        o3.register_user(self.u3)
        self.assertEqual(Org.objects.members_count(o3), 2)
        o3.de_register_user(self.u3)
        self.assertEqual(Org.objects.members_count(o3), 1)
        self.assertEqual(o3.member_count(), 1)
        self.assertFalse(o3.is_member(self.u3))
        self.assertEqual(Org.objects.user_orgs_ids(self.u3).first(), o2.id)

    def testOrgMembersCsvView(self):
        Org.objects.create_org(name='My Org 2', created_by=self.u2)
        o3 = Org.objects.create_org(name='My Org 4', created_by=self.u2)
        o3.register_user(self.u3)
        self.assertEqual(Org.objects.members_count(o3), 2)
        url = reverse('org:export-member-csv', kwargs={'slug': o3.slug})

        self.client.login(email=self.u2.email, password='pass')
        resp = self.client.get(url)
        self.assertContains(resp, "User Two")
        self.assertContains(resp, self.u2.email)
        self.assertContains(resp, "User Three")
        self.assertContains(resp, self.u3.email)
        self.client.logout()

    def testEmailList(self):
        o2 = Org.objects.create_org(name='My Org 2', created_by=self.u2)
        o2.register_user(self.u3)
        u4 = self.create_user('user4', 'user4@foo.com')
        o2.register_user(u4)
        emails = o2.get_email_list()
        self.assertTrue(len(emails), 1)
        self.assertEqual(emails[0], 'user2@foo.com')
        emails = o2.get_email_list(False)
        self.assertTrue(len(emails), 3)
        self.assertTrue('user2@foo.com' in emails)
        self.assertTrue('user3@foo.com' in emails)
        self.assertTrue('user4@foo.com' in emails)

        # Test that inactive user is ot included
        u4.is_active = False
        u4.save()
        emails = o2.get_email_list(False)
        self.assertTrue(len(emails), 2)
        self.assertTrue('user2@foo.com' in emails)
        self.assertTrue('user3@foo.com' in emails)

        # Test that inactive membership is not included
        u3_membership = o2.get_membership_obj(self.u3)
        u3_membership.is_active = False
        u3_membership.save()
        emails = o2.get_email_list(False)
        self.assertTrue(len(emails), 1)
        self.assertTrue('user2@foo.com' in emails)

    def testUserStatusManagement(self):
        o1 = Org.objects.create_org(name='My Org 5', created_by=self.u1)
        u4 = self.create_user('user4', 'user4@foo.com')

        o1.register_user(self.u2)
        o1.register_user(self.u3)
        o1.register_user(u4)

        u4_membership = o1.get_membership_obj(u4)
        u4_membership.role = 'a1'
        u4_membership.is_org_admin = True
        u4_membership.save()
        o1.set_permission(user=u4, permission='can_manage_users', value=True)

        self.assertTrue(o1.has_permission(self.u1, 'can_manage_users'))
        self.assertFalse(o1.has_permission(self.u2, 'can_manage_users'))
        self.assertFalse(o1.has_permission(self.u3, 'can_manage_users'))
        self.assertTrue(o1.has_permission(u4, 'can_manage_users'))

        # Set u2 as an inactive member
        u2_membership = o1.get_membership_obj(self.u2)
        u2_membership.is_active = False
        u2_membership.save()

        url = reverse('org:members', kwargs={'slug': o1.slug})

        resp = self.client.get(url)
        self.assertRedirects(resp, expected_url='/account/login/?next=' + url, status_code=302, target_status_code=200)

        # Ensure that u3 (can't manage users) cannot see u2 (disabled) in the members list
        self.client.login(email='user3@foo.com', password='pass')
        resp = self.client.get(url)
        self.assertNotContains(resp, "User Two")
        self.client.logout()

        # Ensure that u1 (owner) sees u2 (disabled) in the members list
        self.client.login(email='user1@foo.com', password='pass')
        resp = self.client.get(url)
        self.assertContains(resp, "User Two")
        self.client.logout()

        # Ensure that u4 (admin) can edit u2 and u3, but not u1 (owner)
        u1_edit_url = o1.get_membership_obj(self.u1).get_edit_url()
        u2_edit_url = o1.get_membership_obj(self.u2).get_edit_url()
        u3_edit_url = o1.get_membership_obj(self.u3).get_edit_url()
        self.client.login(email='user4@foo.com', password='pass')
        resp = self.client.get(url)
        self.assertNotContains(resp, u1_edit_url)
        self.assertContains(resp, u2_edit_url)
        self.assertContains(resp, u3_edit_url)
        self.client.logout()

        # Ensure that u1 (owner) cannot disable the owner (u1)
        u1_edit_url = o1.get_membership_obj(self.u1).get_edit_url()
        self.client.login(email='user1@foo.com', password='pass')
        payload = {'is_active': False, 'role': 'a0', 'submit': "Change"}
        resp = self.client.post(u1_edit_url, payload)
        self.assertContains(resp, 'Owner cannot be disabled. Please downgrade this user first.')
        self.client.logout()

        # Ensure that u1 (owner) cannot downgrade the owner (u1) without making another owner
        u1_edit_url = o1.get_membership_obj(self.u1).get_edit_url()
        self.client.login(email='user1@foo.com', password='pass')
        payload = {'is_active': True, 'role': 'a1', 'submit': "Change"}
        resp = self.client.post(u1_edit_url, payload)
        self.assertNotContains(resp, 'Owner cannot be disabled. Please downgrade this user first.')
        self.assertContains(resp, "Cannot remove owner: organization must have an owner.")
        self.client.logout()

        # Ensure that u1 (owner) can make another user owner, then downgrade u1 (owner)
        org_membership_url = reverse('org:members', kwargs={'slug': o1.slug})
        u2_edit_url = o1.get_membership_obj(self.u2).get_edit_url()
        self.client.login(email='user1@foo.com', password='pass')
        payload = {'is_active': True, 'role': 'a0', 'submit': "Change"}
        resp = self.client.post(u2_edit_url, payload)
        self.assertRedirects(resp, expected_url=org_membership_url, status_code=302, target_status_code=200)
        u1_edit_url = o1.get_membership_obj(self.u1).get_edit_url()
        payload = {'is_active': True, 'role': 'a1', 'submit': "Change"}
        resp = self.client.post(u1_edit_url, payload)
        self.assertRedirects(resp, expected_url=org_membership_url, status_code=302, target_status_code=200)
        self.client.logout()

    def testBasicOrgGet(self):

        o1 = Org.objects.create(name='My Org', created_by=self.u2)
        url = reverse('org:detail', kwargs={'slug':o1.slug})
        resp = self.client.get(url)
        self.assertRedirects(resp, expected_url='/account/login/?next='+url, status_code=302, target_status_code=200)

        self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testOrgPost(self):

        url = reverse('org:create')
        payload = {'name': 'Org 1', 'is_org_admin': True}

        self.assertEqual(Org.objects.count(), 0)

        resp = self.client.post(url, payload)
        self.assertRedirects(resp, expected_url='/account/login/?next='+url, status_code=302, target_status_code=200)

        self.assertEqual(Org.objects.count(), 0)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertEqual(ok, True)

        resp = self.client.post(url, payload)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)

        self.assertEqual(Org.objects.count(), 1)
        org = Org.objects.first()
        self.assertTrue(org.is_member(self.u2))
        membership = OrgMembership.objects.get(org=org, user=self.u2)
        self.assertTrue(membership.is_org_admin)

    def testOrgDuplicatesOnCreate(self):
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertEqual(ok, True)
        self.assertEqual(Org.objects.count(), 0)
        url = reverse('org:create')
        payload = {'name': 'Org 1'}

        resp = self.client.post(url, payload)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(Org.objects.count(), 1)
        org = Org.objects.first()
        self.assertEqual(org.slug, 'org-1')

        # Name duplicates not allowed
        resp = self.client.post(url, payload)
        self.assertContains(resp, 'Company Name already exists', status_code=200)
        self.assertEqual(Org.objects.count(), 1)

        # Different Name, but duplicate slug
        payload = {'name': 'Org-1'}
        self.assertContains(resp, 'Company Name already exists', status_code=200)
        self.assertEqual(Org.objects.count(), 1)

    def testOrgDuplicatesOnEdit(self):
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertEqual(ok, True)
        org1 = Org.objects.create(name='Org 1', created_by=self.u1)
        org2 = Org.objects.create_org(name='Org 2', created_by=self.u2)
        self.assertEqual(Org.objects.count(), 2)

        # Try to rename Org2 to Org1's name
        url = reverse('org:edit', kwargs={'slug': org2.slug})
        payload = {'name': 'Org 3'}

        resp = self.client.post(url, payload)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(Org.objects.count(), 2)
        org1 = Org.objects.first()
        org2 = Org.objects.last()
        self.assertEqual(org1.name, 'Org 1')
        self.assertEqual(org1.slug, 'org-1')
        self.assertEqual(org2.name, 'Org 3')
        self.assertEqual(org2.slug, 'org-3')

        # Try to rename Org3 to Org1's name
        url = reverse('org:edit', kwargs={'slug': 'org-3'})
        payload = {'name': 'Org 1'}
        resp = self.client.post(url, payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Org.objects.count(), 2)
        org1 = Org.objects.first()
        org2 = Org.objects.last()
        self.assertEqual(org1.name, 'Org 1')
        self.assertEqual(org1.slug, 'org-1')
        self.assertEqual(org2.name, 'Org 3')
        self.assertEqual(org2.slug, 'org-3')

    def testBasicOrgMembershipObject(self):
        o1 = Org.objects.create(name='My Org', created_by=self.u2)
        self.assertEqual(OrgMembership.objects.count(), 0)
        self.assertFalse(o1.is_member(self.u2))
        OrgMembership.objects.create(org=o1, user=self.u2)
        self.assertEqual(OrgMembership.objects.count(), 1)
        self.assertTrue(o1.is_member(self.u2))
        self.assertEqual(o1.users.first(), self.u2)

    def testBasicOrgMembershipEdit(self):
        o1 = Org.objects.create_org(name='My Org 1', created_by=self.u2)
        m = OrgMembership.objects.create(org=o1, user=self.u3, permissions=ORG_ROLE_PERMISSIONS['m1'])
        self.assertFalse(m.is_org_admin)
        self.assertTrue(o1.is_member(self.u2))
        self.assertTrue(o1.is_member(self.u3))
        self.assertTrue(o1.is_admin(self.u2))
        self.assertFalse(o1.is_admin(self.u3))

        url = reverse('org:member-edit', kwargs={'pk':str(m.id)})
        resp = self.client.get(url)
        self.assertRedirects(resp, expected_url='/account/login/?next='+url, status_code=302, target_status_code=200)

        self.client.login(email='user1@foo.com', password='pass')

        resp = self.client.get(url)
        # Staff can edit
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

        self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(o1.get_membership_obj(self.u2), 'a1')

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertContains(resp, 'm1', status_code=200)
        self.assertContains(resp, 'a1', status_code=200)
        # self.assertNotContains(resp, 'a0', status_code=200)

        payload = {'role' : 'a1',
                   'status' : True}
        response = self.client.post(url, payload)
        self.assertRedirects(response, expected_url=o1.get_membership_url(), status_code=302, target_status_code=200)
        m = OrgMembership.objects.get(org=o1, user=self.u3)
        self.assertTrue(o1.get_membership_obj(self.u2), 'a1')

        self.client.logout()

        self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        o1.register_user(self.u3, role='r1')
        self.assertFalse(o1.has_permission(self.u3, 'can_manage_users'))
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

    def testProjectMemberPageAccess(self):
        """
        Ensure we can call GET project page
        """

        o1 = Org.objects.create_org(name='My Org 1', created_by=self.u2)

        detail_url = reverse('org:detail', kwargs={'slug':o1.slug})
        members_url = reverse('org:members', kwargs={'slug':o1.slug})

        self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.get(members_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        o1.register_user(self.u3)

        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(members_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testOrgManager(self):
        o1 = Org.objects.create_org(name='My Org', created_by=self.u2)
        self.assertEqual(Org.objects.count(), 1)
        self.assertEqual(OrgMembership.objects.count(), 1)
        self.assertEqual(OrgMembership.objects.filter(user=self.u2).count(), 1)
        self.assertEqual(OrgMembership.objects.filter(org=o1).count(), 1)
        self.assertEqual(Org.objects.members_count(o1), 1)
        self.assertEqual(Org.objects.members_qs(o1).first(), self.u2)
        self.assertTrue(o1.is_member(self.u2))

    def testOrgDomain(self):
        o1 = Org.objects.create_org(name='My Org', created_by=self.u2)
        domain1 = OrgDomain.objects.create(name='org.com', org=o1)
        domain2 = OrgDomain.objects.create(name='org2.com', org=o1, default_role='r1')
        self.assertFalse(domain1.verified)
        self.assertFalse(domain2.verified)
        self.assertEqual(o1.domains.count(), 2)

        self.assertFalse(o1.is_member(self.u3))
        domain1.process_new_user(self.u3)
        self.assertTrue(o1.is_member(self.u3))
        self.assertEqual(o1.get_membership_obj(self.u3).role, 'm1')

        # Test we do not downgrade user if they change email
        domain2.process_new_user(self.u3)
        self.assertTrue(o1.is_member(self.u3))
        self.assertEqual(o1.get_membership_obj(self.u3).role, 'm1')

    def testRolesPage(self):
        o1 = Org.objects.create_org(name='My Org 1', created_by=self.u2)

        url = reverse('org:roles', kwargs={'slug':o1.slug})

        resp = self.client.get(url)
        self.assertRedirects(resp, expected_url='/account/login/?next='+url, status_code=302, target_status_code=200)

        self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testSearchPage(self):
        o1 = Org.objects.create_org(name='My Org 1', created_by=self.u2)

        url = reverse('org:search', kwargs={'slug': o1.slug})

        self.client.login(email='user3@foo.com', password='pass')
        self.assertFalse(o1.is_member(self.u3))
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(o1.is_member(self.u2))
        resp = self.client.get(url)
        self.assertContains(resp, 'Search', status_code=200)

        # No device indexed
        resp = self.client.post(url, {'q': 'd'})
        self.assertContains(resp, 'No results found.', status_code=200)

        p1 = Project.objects.create(name='Project 1', created_by=self.u2, org=o1)
        Device.objects.create(id=0x100, project=p1, created_by=self.u2, org=o1)
        resp = self.client.post(url, {'q': 'd'})
        self.assertContains(resp, 'Devices', status_code=200)

    def testMemberMessages(self):
        """
        Ensure we can send member emails
        """

        o1 = Org.objects.create_org(name='My Org 1', created_by=self.u2)

        url = reverse('org:member-message', kwargs={'slug':o1.slug})

        self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        o1.register_user(self.u3)
        self.assertFalse(o1.has_permission(self.u3, 'can_manage_users'))
        self.assertFalse(o1.has_permission(self.u3, 'can_manage_org_and_projects'))

        resp = self.client.get(url)
        self.assertRedirects(resp, expected_url=o1.get_absolute_url(), status_code=302, target_status_code=200)

        o1.set_permission(self.u3, 'can_manage_users', True)
        self.assertTrue(o1.has_permission(self.u3, 'can_manage_users'))

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()
