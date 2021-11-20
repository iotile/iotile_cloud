import datetime

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core import mail
from django.forms import ValidationError
from django.utils import timezone

from rest_framework import status
from allauth.account.models import EmailAddress

from apps.org.models import *
from apps.utils.test_util import TestMixin

from .models import *
from .adapter import InvitationAdapter

user_model = get_user_model()


class InvitationTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()

    def tearDown(self):
        self.orgTestTearDown()
        self.userTestTearDown()
        Invitation.objects.all().delete()

    def testManager(self):
        Invitation.objects.create_invitation(org=self.o2, email='test@foo.com', sent_by=self.u2)
        self.assertEqual(Invitation.objects.count(), 1)

    def testInviteForm(self):
        url = reverse('org:invitation:invite', kwargs={'org_slug': self.o2.slug})
        response = self.client.get(url)
        self.assertRedirects(response, expected_url='/account/login/?next=/org/{0}/invitation/invite/'.format(
            self.o2.slug
        ))

        self.assertEqual(Invitation.objects.count(), 0)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertEqual(ok, True)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertTrue(self.o2.has_access(self.u2))
        payload = {
            'email': 'test@example.com',
            'role': 'r1'
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(Invitation.objects.count(), 1)

        self.client.logout()

    def testDuplicates(self):
        url = reverse('org:invitation:invite', kwargs={'org_slug': self.o2.slug})

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertEqual(ok, True)

        self.assertTrue(self.o2.has_access(self.u2))
        payload = {
            'email': 'test@example.com',
            'role': 'm1'
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(Invitation.objects.count(), 1)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url, payload)
        self.assertContains(response, 'Invitation already exists for {}'.format(payload['email']), status_code=200)
        self.assertEqual(Invitation.objects.count(), 1)

        self.client.logout()

        url = reverse('org:invitation:invite', kwargs={'org_slug': self.o3.slug})

        # Another user can still invite same email
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertEqual(ok, True)

        self.assertTrue(self.o3.has_access(self.u3))
        payload = {
            'email': 'test@example.com',
            'role': 'r1'
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(Invitation.objects.count(), 2)
        invitation = Invitation.objects.last()
        self.assertEqual(invitation.role, 'r1')
        self.assertFalse(invitation.accepted)

        response = self.client.post(url, payload)
        self.assertContains(response, 'Invitation already exists for {}'.format(payload['email']), status_code=200)
        self.assertEqual(Invitation.objects.count(), 2)

        self.client.logout()

    def testUserAlreadyExists(self):
        old_user = user_model.objects.create_superuser(username='old', email='old@foo.com', password='pass')
        old_user.is_active = True
        old_user.save()
        EmailAddress.objects.create(email='old@foo.com', user=old_user)
        self.o2.register_user(old_user)

        url = reverse('org:invitation:invite', kwargs={'org_slug': self.o2.slug})

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertEqual(ok, True)

        self.assertTrue(self.o2.has_access(self.u2))
        payload = {
            'email': old_user.email,
            'role': 'r1'
        }
        response = self.client.post(url, payload)
        self.assertContains(response, 'User with email {0} is already a member of Organization'.format(payload['email']), status_code=200)
        self.assertEqual(Invitation.objects.count(), 0)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testAcceptFlow(self):
        invitation = Invitation.objects.create_invitation(org=self.o2, email='test@foo.com', sent_by=self.u2)
        self.assertEqual(Invitation.objects.count(), 1)

        session_invitation_id = self.client.session.get('invitation_id')
        account_verified_email = self.client.session.get('account_verified_email')
        self.assertIsNone(session_invitation_id)
        self.assertIsNone(account_verified_email)

        url = reverse('org:invitation:accept', kwargs={'org_slug': self.o2.slug, 'pk': str(invitation.id)})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = {}
        response = self.client.post(url, payload)
        self.assertRedirects(response, expected_url='/account/signup/')

        session_invitation_id = self.client.session.get('invitation_id')
        account_verified_email = self.client.session.get('account_verified_email')
        self.assertEqual(session_invitation_id, str(invitation.id))
        self.assertEqual(account_verified_email, invitation.email)

        self.assertEqual(Invitation.objects.count(), 1)
        invitation = Invitation.objects.first()
        invitation.accepted = True
        invitation.save()

        # Cannot accept twice
        url = reverse('org:invitation:accept', kwargs={'org_slug': self.o2.slug, 'pk': str(invitation.id)})
        response = self.client.get(url)
        self.assertRedirects(response, expected_url='/', status_code=302, target_status_code=302)
        response = self.client.post(url, payload)
        self.assertRedirects(response, expected_url='/', status_code=302, target_status_code=302)

    def testDeleteForm(self):
        i = Invitation.objects.create_invitation(org=self.o2, email='test@foo.com', sent_by=self.u2)
        self.assertEqual(Invitation.objects.count(), 1)
        url = reverse('org:invitation:delete', kwargs={'pk': i.id, 'org_slug': self.o2.slug, })

        response = self.client.get(url)
        self.assertRedirects(response, expected_url='/account/login/?next=/org/{0}/invitation/{1}/delete/'.format(
            self.o2.slug, i.id
        ))

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertEqual(ok, True)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(Invitation.objects.count(), 0)

        self.client.logout()


    def testResendForm(self):
        i = Invitation.objects.create(org=self.o2, email='test@foo.com', sent_by=self.u2, sent_on=timezone.now() - datetime.timedelta(days=30))
        self.assertEqual(Invitation.objects.count(), 1)
        self.assertEqual(Invitation.objects.pending_invitations().count(), 1)
        self.assertEqual(Invitation.objects.expired_invitations().count(), 1)
        url = reverse('org:invitation:resend', kwargs={'org_slug': self.o2.slug, 'pk': i.id})

        response = self.client.get(url)
        self.assertRedirects(response, expected_url='/account/login/?next=/org/{0}/invitation/{1}/resend/'.format(
            self.o2.slug, i.id
        ))

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertEqual(ok, True)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(Invitation.objects.pending_invitations().count(), 1)
        self.assertEqual(Invitation.objects.expired_invitations().count(), 0)

        self.client.logout()

    def test_disalloed_domains(self):
        adapter = InvitationAdapter()
        email = adapter.clean_email('test@foo.com')
        self.assertEqual(email, 'test@foo.com')
        email = adapter.clean_email('test@sub.foo.com')
        self.assertEqual(email, 'test@sub.foo.com')
        with self.assertRaises(ValidationError):
            adapter.clean_email('info.avalins.com')
        with self.assertRaises(ValidationError):
            adapter.clean_email('test@info')
        with self.assertRaises(ValidationError):
            adapter.clean_email('test@info.ru')
        with self.assertRaises(ValidationError):
            adapter.clean_email('test@info.avalins.com')
        with self.assertRaises(ValidationError):
            adapter.clean_email('test@avalins.com')

