import json
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from apps.org.models import AuthAPIKey
from apps.utils.api_key_utils import get_apikey_object_from_generated_key
from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()


class DeviceTemplateAPIKeyTestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.o1 = Org.objects.create_org(name='My Org 1', created_by=self.u1)
        self.o2 = Org.objects.create_org(name='My Org 2', created_by=self.u1)
        self.api_key, self.generated_key = AuthAPIKey.objects.create_key(name="API key unit test", org=self.o1)

        # Create a DT for o1 and a DT for o2
        self.dt1 = DeviceTemplate.objects.create_template(external_sku='Device 1',
                                                    released_on=timezone.now(), major_version=2,
                                                    os_tag=2050, os_major_version=1, os_minor_version=2,
                                                    hw_tag=1024, hw_major_version=1,
                                                    created_by=self.u1, org=self.o1)
        self.c1 = Component.objects.create(external_sku='Comp 1', type='IOT', created_by=self.u1)

        self.dt2 = DeviceTemplate.objects.create_template(external_sku='Device 2',
                                                    released_on=timezone.now(), patch_version=3,
                                                    created_by=self.u1, org=self.o2)
        self.c2 = Component.objects.create(external_sku='Comp 2', type='IOT', created_by=self.u1)
        self.dts = {self.dt1.slug: self.dt1, self.dt2.slug: self.dt2}

    def tearDown(self):
        Component.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()
        AuthAPIKey.objects.all().delete()

    def assertIsSameDt(self, dt1, dt2: DeviceTemplate):
        """
        Returns true if DTs are the same

        dt1 = dictionary, dt2 = DeviceTemplate object
        """
        self.assertEqual(dt1['slug'], dt2.slug)
        self.assertEqual(dt1['external_sku'], dt2.external_sku)
        self.assertEqual(dt1['org'], dt2.org.slug)

        self.assertEqual(dt1['version'], dt2.version)
        self.assertEqual(dt1['os_tag'], dt2.os_tag)
        self.assertEqual(dt1['os_version'], dt2.os_version)
        self.assertEqual(dt1['hw_tag'], dt2.hw_tag)
        self.assertEqual(dt1['hw_version'], dt2.hw_version)

    def testGetWithAPIKey(self):
        """
        Ensure that we can get a DT with an API key
        """
        url = '/api/v1/dt/'
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        self.assertEqual(len(deserialized['results']), 2)
        for resultDt in deserialized['results']:
            self.assertIsSameDt(resultDt, self.dts[resultDt['slug']])

    def testAPIKeyOtherApis(self):
        """
        Ensure that API call fails on non-GET calls of a key/token-enabled API
        """

        url = '/api/v1/dt/'
        payload = {
            'external_sku': 'foo',
            'org': str(self.o1.slug),
            'major_version': 2, 'patch_version': 1,
            'os_tag': 2050,
            'os_major_version': 1,
            'hw_tag': 1024,
            'hw_major_version': 1,
            'released_on': '2016-09-23'
        }
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.put(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.patch(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.delete(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetAnotherOrgDt(self):
        """
        Ensure that we can get DT info belonging to a different org
        """
        url = '/api/v1/dt/'
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }

        # Verify that you can get DT information belonging to o2 (apikey is registered to o1)
        response = self.client.get(url+'?org__slug={}'.format(self.o2.slug), **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

    def testActive(self):
        dt_inactive = DeviceTemplate.objects.create_template(external_sku='Device test inactive',
                                                             released_on=timezone.now(),
                                                             active=False,
                                                             created_by=self.u1, org=self.o1)
        url = '/api/v1/dt/'
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)
        self.assertEqual(len(deserialized['results']), 2)
        for resultDt in deserialized['results']:
            self.assertIsSameDt(resultDt, self.dts[resultDt['slug']])

    def testRevokedAPIKey(self):
        """
        Ensure that we cannot use a revoked API key
        """
        url = '/api/v1/dt/'
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }
        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        apikey = get_apikey_object_from_generated_key(self.generated_key)
        apikey.revoked = True
        apikey.save()

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testExpiredAPIKey(self):
        """
        Ensure that we cannot use an expired API key
        """
        url = '/api/v1/dt/'
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }
        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        apikey = get_apikey_object_from_generated_key(self.generated_key)
        apikey.expiry_date = datetime.now() - timedelta(days=1)
        apikey.save()

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
