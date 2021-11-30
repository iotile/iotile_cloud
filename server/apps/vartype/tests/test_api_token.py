import json
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.org.models import AuthAPIKey, Org
from apps.utils.api_key_utils import get_apikey_object_from_generated_key
from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()


class VarTypeAPIKeyTestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.o1 = Org.objects.create_org(name='My Org 1', created_by=self.u1)
        self.o2 = Org.objects.create_org(name='My Org 2', created_by=self.u1)
        self.api_key, self.generated_key = AuthAPIKey.objects.create_key(name="API key unit test", org=self.o1)

        # Create a VT with input and output units
        self.vt1 = VarType.objects.create(
            name='Volume',
            storage_units_full='Liters',
            created_by=self.u1
        )
        self.input_unit1 = VarTypeInputUnit.objects.create(
            var_type=self.vt1,
            unit_full='Liters',
            unit_short='l',
            m=1,
            d=2,
            created_by=self.u1
        )
        self.input_unit2 = VarTypeInputUnit.objects.create(
            var_type=self.vt1,
            unit_full='Gallons',
            unit_short='g',
            m=4,
            d=2,
            created_by=self.u1
        )
        self.output_unit = VarTypeOutputUnit.objects.create(
            var_type=self.vt1,
            unit_full='Foo',
            unit_short='f',
            m=2,
            created_by=self.u1
        )

    def tearDown(self):
        VarType.objects.all().delete()
        self.projectTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()
        AuthAPIKey.objects.all().delete()

    def assertVtIsSame(self, response_vt, actual_vt: VarType, input_units, output_units):
        '''
        Parameters:

        response_vt - dict (result from API call)
        actual_vt - VarType
        input_units - list of VarTypeInputUnit
        output_units - list of VarTypeOutputUnit
        '''
        self.assertEqual(response_vt['name'], actual_vt.name)
        self.assertEqual(response_vt['slug'], actual_vt.slug)
        self.assertEqual(response_vt['storage_units_full'], actual_vt.storage_units_full)
        self.assertEqual(response_vt['stream_data_type'], actual_vt.stream_data_type)
        # TODO check input and output units

    def testGetWithAPIKey(self):
        """
        Ensure that we can get VarType info with an API key
        """
        url = reverse('vartype-list')
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.assertEqual(len(deserialized['results']), 1)
        resultVt = deserialized['results'][0]
        self.assertVtIsSame(
            resultVt, self.vt1,
            [self.input_unit1, self.input_unit2],
            [self.output_unit]
        )

    def testAPIKeyOtherApis(self):
        """
        Ensure that API call fails on non-GET calls of a key/token-enabled API
        """

        url = reverse('vartype-list')
        payload = {
            "name": "test vartype",
            "storage_units_full": "test unit"
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

    def testRevokedAPIKey(self):
        """
        Ensure that we cannot use a revoked API key
        """
        url = reverse('vartype-list')
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
        url = reverse('vartype-list')
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

    def testGetDetailWithAPIKey(self):
        """
        Ensure that we can get VarType info with an API key
        """
        url = reverse('vartype-detail', kwargs={'slug': self.vt1.slug})
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertVtIsSame(
            deserialized, self.vt1,
            [self.input_unit1, self.input_unit2],
            [self.output_unit]
        )
