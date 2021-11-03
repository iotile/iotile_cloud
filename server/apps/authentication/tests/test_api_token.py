import json

from django.conf import settings
from django.contrib.auth import get_user_model

from rest_framework.test import APIClient
from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.org.models import Org, AuthAPIKey
from apps.utils.test_util import TestMixin

from ..api_views import *

user_model = get_user_model()


class AccountAPIKeyTests(TestMixin, APITestCase):

    def setUp(self):
        self.u1 = user_model.objects.create_superuser(username='user1', email='user1@foo.com', password='pass')
        self.u1.is_active = True
        self.u1.is_staff = True
        self.u1.name = 'User One'
        self.u1.save()
        self.o1 = Org.objects.create_org(name='My Org 1', created_by=self.u1)
        self.o2 = Org.objects.create_org(name='My Org 2', created_by=self.u1)
        self.api_key, self.generated_key = AuthAPIKey.objects.create_key(name="API key unit test", org=self.o1)

    def tearDown(self):
        AuthAPIKey.objects.all().delete()
        self.projectTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def test_generate_api_key(self):
        """
        Ensure that we can create, use, and delete an API key
        """
        url = reverse('sensorgraph-list')
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_wrong_api_key(self):
        """
        Ensure that API call fails with wrong API key (when not logged in)
        """
        url = reverse('sensorgraph-list')
        generated_key = "abcdefg"
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(generated_key)
        }

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_generate_api_key(self):
        """
        Ensure that we can log in and still use the API key
        """
        url = reverse('sensorgraph-list')
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }
        ok = self.client.login(email=self.u1.email, password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.logout()

    def test_wrong_api(self):
        """
        Ensure that API call fails on API where key is not enabled
        (that not all API calls are affected by the API key/token)
        """
        # Try another public API
        url = reverse('orgtemplate-list')
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # Try a "regular" API
        url = reverse('sensorgraph:list')
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }

        response = self.client.get(url, **auth_headers)
        self.assertRedirects(response, '/account/login/?next={0}'.format(url))

    def test_post_get(self):
        """
        Ensure that API call fails on POST of a key/token-enabled API
        """

        payload = {
            'name': 'foo',
            'app_tag': 1027,
            'app_major_version': 2,
            'major_version': 3,
            'patch_version': 1,
            'org': str(self.o1.slug)
        }

        url = reverse('sensorgraph-list')
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }
        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_put_get(self):
        """
        Ensure that API call fails on PUT of a key/token-enabled API
        """

        payload = {
            'name': 'foo',
            'app_tag': 1027,
            'app_major_version': 2,
            'major_version': 3,
            'patch_version': 1,
            'org': str(self.o1.slug)
        }

        url = reverse('sensorgraph-list')
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }
        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.put(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patch_get(self):
        """
        Ensure that API call fails on PATCH of a key/token-enabled API
        """

        payload = {
            'name': 'foo',
            'app_tag': 1027,
            'app_major_version': 2,
            'major_version': 3,
            'patch_version': 1,
            'org': str(self.o1.slug)
        }

        url = reverse('sensorgraph-list')
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }
        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.patch(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_delete_get(self):
        """
        Ensure that API call fails on DELETE of a key/token-enabled API
        """

        url = reverse('sensorgraph-list')
        payload = {
            'name': 'foo',
            'app_tag': 1027,
            'app_major_version': 2,
            'major_version': 3,
            'patch_version': 1,
            'org': str(self.o1.slug)
        }
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }
        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.delete(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
