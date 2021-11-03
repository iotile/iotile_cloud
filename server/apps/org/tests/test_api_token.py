
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from rest_framework import status

from apps.utils.test_util import TestMixin

user_model = get_user_model()

class OrgAPIKeyTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()

        self.admin = user_model.objects.create_superuser(username='admin', email='admin@acme.com', password='pass')
        self.admin.is_active = True
        self.admin.save()
        self.assertTrue(self.admin.is_admin)
        self.assertTrue(self.admin.is_staff)

        self.staff = user_model.objects.create_user(username='staff', email='staff@acme.com', password='pass')
        self.staff.is_active = True
        self.staff.is_admin = False
        self.staff.is_staff = True
        self.staff.save()

        self.member = user_model.objects.create_user(username='member', email='member@acme.com', password='pass')
        self.member.is_active = True
        self.member.is_admin = False
        self.member.is_staff = False
        self.member.save()

        self.user = user_model.objects.create_user(username='user', email='user@acme.com', password='pass')
        self.user.is_active = True
        self.user.is_admin = False
        self.user.is_staff = False
        self.user.save()

    def tearDown(self):
        self.orgTestTearDown()
        self.userTestTearDown()

    def test_access_controls(self):

        url_list = [
            reverse('org:apikeys', kwargs={'slug': self.o2.slug}),
            reverse('org:apikey-add', kwargs={'slug': self.o2.slug}),
        ]
        for url in url_list:
            response = self.client.get(url)
            self.assertRedirects(response, '/account/login/?next={0}'.format(url))

            # Admin user
            ok = self.client.login(email='admin@acme.com', password='pass')
            self.assertTrue(ok)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.client.logout()

            # Staff user
            ok = self.client.login(email='staff@acme.com', password='pass')
            self.assertTrue(ok)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.client.logout()

            # User that is a member of the org
            self.o2.register_user(self.member, role='m1')

            ok = self.client.login(email='member@acme.com', password='pass')
            self.assertTrue(ok)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

            self.client.logout()

            # User that is not a member of the org
            ok = self.client.login(email='user@acme.com', password='pass')
            self.assertTrue(ok)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

            self.client.logout()

            # Org Owner
            self.assertEqual(self.u2.is_staff, False)
            self.assertEqual(self.u2.is_admin, False)
            ok = self.client.login(email=self.u2.email, password='pass')
            self.assertTrue(ok)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.client.logout()
