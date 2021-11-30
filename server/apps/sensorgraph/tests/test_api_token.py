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


class SensorGraphAPIKeyTestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.o1 = Org.objects.create_org(name='My Org 1', created_by=self.u1)
        self.o2 = Org.objects.create_org(name='My Org 2', created_by=self.u1)
        self.api_key, self.generated_key = AuthAPIKey.objects.create_key(name="API key unit test", org=self.o1)

        # Create an SG for o1 and an SG for o2
        self.vt = VarType.objects.create(name="test vartype",
                                    storage_units_full="test unit",
                                    created_by=self.u1)
        self.sg1 = SensorGraph.objects.create_graph(name='SG 1', created_by=self.u1, org=self.o1)
        self.variable1 = VariableTemplate.objects.create(sg=self.sg1, created_by=self.u1, label='Var1', var_type=self.vt)
        self.widget1 = DisplayWidgetTemplate.objects.create(sg=self.sg1, created_by=self.u1, label='Widget 1')

        self.sg2 = SensorGraph.objects.create_graph(name='SG 2', created_by=self.u1, org=self.o2)
        self.variable2 = VariableTemplate.objects.create(sg=self.sg2, created_by=self.u1, label='Var2', var_type=self.vt)
        self.widget2 = DisplayWidgetTemplate.objects.create(sg=self.sg2, created_by=self.u1, label='Widget 2')
        self.sgs = {
            self.sg1.slug: [self.sg1, [self.widget1], [self.variable1]],
            self.sg2.slug: [self.sg2, [self.widget2], [self.variable2]],
        }

    def tearDown(self):
        SensorGraph.objects.all().delete()
        VariableTemplate.objects.all().delete()
        DisplayWidgetTemplate.objects.all().delete()
        VarType.objects.all().delete()
        self.projectTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()
        AuthAPIKey.objects.all().delete()

    def assertSGIsSame(self, resultSg, expectedSg: SensorGraph, widgets, variable_templates):
        self.assertEqual(resultSg['name'], expectedSg.name)
        self.assertEqual(resultSg['org'], expectedSg.org.slug)

        self.assertEqual(len(resultSg['display_widget_templates']), len(widgets))
        if len(widgets) == 1:
            self.assertEqual(resultSg['display_widget_templates'][0]['label'], widgets[0].label)
        self.assertEqual(len(resultSg['variable_templates']), len(variable_templates))
        if len(variable_templates) == 1:
            self.assertEqual(resultSg['variable_templates'][0]['label'], variable_templates[0].label)
        # TODO properly check multiple widgets and variable templates

    def testGetWithAPIKey(self):
        """
        Ensure that we can get SG info with an API key
        """
        url = reverse('sensorgraph-list')
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        self.assertEqual(len(deserialized['results']), 2)
        for resultSg in deserialized['results']:
            expected = self.sgs[resultSg['slug']]
            self.assertSGIsSame(resultSg, expected[0], expected[1], expected[2])

    def testAPIKeyOtherApis(self):
        """
        Ensure that API call fails on non-GET calls of a key/token-enabled API
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

        response = self.client.post(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.put(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.patch(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.delete(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetAnotherOrgSg(self):
        """
        Ensure that we can get SG info belonging to a different org
        """
        url = reverse('sensorgraph-list')
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key)
        }

        # Verify that you cannot get SG information belonging to o2 (apikey is registered to o1)
        response = self.client.get(url+'?slug={}'.format(self.sg2.slug), **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.assertEqual(len(deserialized['results']), 1)
        resultSg = deserialized['results'][0]
        self.assertSGIsSame(resultSg, self.sg2, [self.widget2], [self.variable2])

    def testRevokedAPIKey(self):
        """
        Ensure that we cannot use a revoked API key
        """
        url = reverse('sensorgraph-list')
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
        url = reverse('sensorgraph-list')
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
