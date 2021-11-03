
import json

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin
from apps.invitation.models import Invitation

from ..models import *

user_model = get_user_model()


class OrgAPITests(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()

    def tearDown(self):
        Org.objects.all().delete()
        OrgMembership.objects.all().delete()
        self.userTestTearDown()

    def testDeleteDevice(self):
        """
        Ensure delete operations are protected
        """
        org = Org.objects.create_org(name='My Org 1', created_by=self.u2)
        url = reverse('org-detail', kwargs={'slug': org.slug})

        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        self.assertEqual(Org.objects.count(), 1)
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Org.objects.count(), 1)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Org.objects.count(), 1)

        resp = self.client.delete(url+'?staff=1')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Org.objects.count(), 0)

        self.client.logout()

    def testPostOrg(self):
        """
        Ensure we can create a new Org object.
        """
        url = reverse('org-list')
        data = {'name':'Org 1'}

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Don't accept duplicate names
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['name'], ['Organization with this Company Name already exists.'])

        # Don't accept duplicate slugs
        data = {'name':'Org-1'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized[0], 'Organization with this Name produces duplicate slug.')

        self.client.logout()

        data = {'name':'Org 2', 'about': "Foo bar"}
        self.assertFalse(Org.objects.filter(name=data['name']).exists())
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertTrue(Org.objects.filter(name=data['name']).exists())
        org = Org.objects.get(slug=deserialized['slug'])
        self.assertTrue(OrgMembership.objects.filter(org=org, user=self.u2).exists())

        self.client.logout()

    def testGetOrg(self):
        """
        Ensure we can call GET on the org API.
        """
        url = reverse('org-list')

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        o1 = Org.objects.create_org(name='My Org 1', created_by=self.u2)
        o2 = Org.objects.create_org(name='My Org 2', created_by=self.u3)
        o3 = Org.objects.create_org(name='My Org 4', created_by=self.u2)
        o3.register_user(self.u3)
        o3.de_register_user(self.u3)
        detail_url = reverse('org-detail', kwargs={'slug': str(o1.slug)})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        resp = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 3)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.get(detail_url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], str(o1.id))
        self.assertEqual(deserialized['name'], str(o1.name))
        self.assertEqual(deserialized['slug'], str(o1.slug))

        self.client.logout()

        # Staff has access to all
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], str(o1.id))

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        detail_url = reverse('org-detail', kwargs={'slug': str(o2.slug)})
        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testGetOrgProjects(self):
        """
        Ensure we can call GET on the projects for a given Org. API
        """
        self.orgTestSetup()
        o4 = Org.objects.create_org(name='My Org 4', created_by=self.u2)
        o4.register_user(self.u3)
        o4.de_register_user(self.u3)
        self.assertEqual(Org.objects.count(), 4)
        self.assertEqual(OrgMembership.objects.count(), 5)
        self.assertEqual(OrgMembership.objects.filter(user=self.u2).count(), 2)
        self.assertEqual(OrgMembership.objects.filter(org=self.o2).count(), 1)

        detail_url = reverse('org-projects', kwargs={'slug': str(self.o2.slug)})

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(detail_url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        self.projectTestSetup()

        resp = self.client.get(detail_url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['slug'], self.p1.slug)
        self.assertEqual(deserialized['results'][0]['id'], str(self.p1.id))

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        detail_url4 = reverse('org-projects', kwargs={'slug': str(o4.slug)})
        resp = self.client.get(detail_url4, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


        self.deviceTemplateTestTearDown()

    def testGetOrgMembership(self):
        """
        Ensure we can call GET on the projects for a given Org. API
        """
        self.o2 = Org.objects.create_org(name='My Org 2', created_by=self.u2)
        self.o3 = Org.objects.create_org(name='My Org 3', created_by=self.u3)
        self.assertEqual(Org.objects.count(), 2)
        self.assertEqual(OrgMembership.objects.count(), 2)
        self.assertEqual(OrgMembership.objects.filter(user=self.u2).count(), 1)
        self.assertEqual(OrgMembership.objects.filter(org=self.o2).count(), 1)

        detail_url = reverse('org-members', kwargs={'slug': str(self.o2.slug)})

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(detail_url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.o2.register_user(self.u3, role='m1')
        self.assertFalse(self.o2.has_permission(self.u3, 'can_manage_users'))
        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.o2.de_register_user(self.u3, delete_obj=True)
        self.o2.register_user(self.u3, role='a0')
        self.assertTrue(self.o2.has_permission(self.u3, 'can_manage_users'))
        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        o2_membership = OrgMembership.objects.get(org=self.o2, user=self.u2)
        o2_membership.is_active = False
        o2_membership.save()

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        resp = self.client.get(detail_url+'?all=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        self.client.logout()

    def testSendInvitation(self):
        """
        Ensure we can call GET on the projects for a given Org. API
        """
        self.o2 = Org.objects.create_org(name='My Org 2', created_by=self.u2)
        self.o3 = Org.objects.create_org(name='My Org 3', created_by=self.u3)
        self.assertEqual(Org.objects.count(), 2)
        self.assertEqual(OrgMembership.objects.count(), 2)
        self.assertEqual(OrgMembership.objects.filter(user=self.u2).count(), 1)
        self.assertEqual(OrgMembership.objects.filter(org=self.o2).count(), 1)
        self.assertTrue(self.o2.is_member(self.u2))
        self.assertTrue(self.o2.is_admin(self.u2))
        u4 = user_model.objects.create_user(username='User4', email='user4@foo.com', password='pass')
        u4.is_active = True
        u4.save()
        u5 = user_model.objects.create_user(username='User5', email='user5@foo.com', password='pass')
        u5.is_active = True
        u5.save()

        detail_url = reverse('org-invite', kwargs={'slug': str(self.o2.slug)})
        payload = {
            'email': 'user10@test.com'
        }

        resp = self.client.post(detail_url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(detail_url+'?staff=1', data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Invitation.objects.count(), 1)
        user10 = Invitation.objects.first()
        self.assertFalse(user10.accepted)
        self.assertEqual(user10.org, self.o2)
        self.assertEqual(user10.sent_by, self.u1)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            'email': 'user20@test.com'
        }

        resp = self.client.post(detail_url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Invitation.objects.count(), 2)
        user20 = Invitation.objects.get(email__contains='user20')
        self.assertFalse(user20.accepted)
        self.assertEqual(user20.org, self.o2)
        self.assertEqual(user20.sent_by, self.u2)

        resp = self.client.post(detail_url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Invitation.objects.count(), 2)
        user20 = Invitation.objects.get(email__contains='user20')
        self.assertFalse(user20.accepted)
        self.assertEqual(user20.org, self.o2)
        self.assertEqual(user20.sent_by, self.u2)

        self.assertEqual(Invitation.objects.pending_invitations().count(), 2)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            'email': 'user20@test.com'
        }

        resp = self.client.post(detail_url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

    def testPostOrgMembership(self):
        """
        Ensure we can call GET on the projects for a given Org. API
        """
        self.o2 = Org.objects.create_org(name='My Org 2', created_by=self.u2)
        self.o3 = Org.objects.create_org(name='My Org 3', created_by=self.u3)
        self.assertEqual(Org.objects.count(), 2)
        self.assertEqual(OrgMembership.objects.count(), 2)
        self.assertEqual(OrgMembership.objects.filter(user=self.u2).count(), 1)
        self.assertEqual(OrgMembership.objects.filter(org=self.o2).count(), 1)
        self.assertTrue(self.o2.is_member(self.u2))
        self.assertTrue(self.o2.is_admin(self.u2))
        u4 = user_model.objects.create_user(username='User4', email='user4@foo.com', password='pass')
        u4.is_active = True
        u4.save()
        u5 = user_model.objects.create_user(username='User5', email='user5@foo.com', password='pass')
        u5.is_active = True
        u5.save()

        detail_url = reverse('org-register', kwargs={'slug': str(self.o2.slug)})
        payload = {
            'user': self.u3.slug
        }

        resp = self.client.post(detail_url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.o2.has_permission(self.u1, 'can_manage_users'))

        resp = self.client.post(detail_url+'?staff=1', data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            'user': u4.slug
        }

        resp = self.client.post(detail_url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        m = OrgMembership.objects.get(user=u4, org=self.o2)
        self.assertEqual(m.role, 'm1')
        self.assertFalse(m.is_org_admin)

        payload = {
            'user': u5.slug,
            'role': 'a0'
        }

        resp = self.client.post(detail_url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        payload['role'] = 'a1'
        resp = self.client.post(detail_url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        m = OrgMembership.objects.get(user=u5, org=self.o2)
        self.assertEqual(m.role, 'a1')
        self.assertTrue(m.is_org_admin)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            'user': u4.slug
        }

        resp = self.client.post(detail_url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

    def testPostOrgMembershipIntegrity(self):
        """
        Ensure we can call GET on the projects for a given Org. API
        """
        self.o2 = Org.objects.create_org(name='My Org 2', created_by=self.u2)

        detail_url = reverse('org-register', kwargs={'slug': str(self.o2.slug)})
        payload = {
            'user': self.u3.slug
        }

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(detail_url+'?staff=1', data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        resp = self.client.post(detail_url+'?staff=1', data=payload)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.logout()

    def testGetOrgExtra(self):
        """
        Test GET /org/slug/extra with extra info
        """
        t1 = OrgTemplate.objects.create_template(name='Master Org 1', created_by=self.u2)

        self.o2 = Org.objects.create_org(name='My Org 2', created_by=self.u2, ot=t1)
        self.assertEqual(Org.objects.count(), 1)
        self.assertEqual(OrgMembership.objects.count(), 1)
        self.assertEqual(OrgMembership.objects.filter(user=self.u2, org=self.o2).count(), 1)

        detail_url = reverse('org-extra', kwargs={'slug': str(self.o2.slug)})

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(detail_url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], str(self.o2.id))

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], str(self.o2.id))
        self.assertEqual(deserialized['ot']['id'], t1.id)
        self.assertEqual(deserialized['current_member']['user'], self.u2.slug)
        self.assertEqual(deserialized['counts']['members'], 1)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

    def testOrgDomain(self):
        o1 = Org.objects.create_org(name='My Org', created_by=self.u2)
        d1 = OrgDomain.objects.create(name='org1.com', org=o1)
        d2 = OrgDomain.objects.create(name='org2.com', org=o1, verified=True)

        url = reverse('org-list')
        detail_url = reverse('org-detail', kwargs={'slug': str(o1.slug)})

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        domains = deserialized['results'][0]['domain_names']
        self.assertEqual(len(domains), 1)
        for domain in domains:
            self.assertTrue(domain == d2.name)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        domains = deserialized['domain_names']
        self.assertEqual(len(domains), 1)
        for domain in domains:
            self.assertTrue(domain == d2.name)

        self.client.logout()
