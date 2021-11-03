import json

from django.contrib.auth import get_user_model

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()

class VariableTemplateAPITestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.sg1 = self.createTestSensorGraph()

    def tearDown(self):
        self.sensorGraphTestTearDown()
        self.projectTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def assertVariableTemplateIsSame(self, request_vt, expected_vt: VariableTemplate):
        self.assertEqual(request_vt['id'], expected_vt.id)
        self.assertEqual(request_vt['label'], expected_vt.label)
        self.assertEqual(request_vt['sg'], expected_vt.sg.slug)
        self.assertEqual(request_vt['lid_hex'], expected_vt.lid_hex)
        self.assertEqual(request_vt['derived_lid_hex'], expected_vt.derived_lid_hex)
        self.assertEqual(request_vt['var_type'], expected_vt.var_type.slug)
        self.assertEqual(request_vt['default_input_unit'], expected_vt.default_input_unit.slug)
        self.assertEqual(request_vt['default_output_unit'], expected_vt.default_output_unit.slug)
        self.assertEqual(request_vt['ctype'], expected_vt.ctype)
        self.assertEqual(request_vt['m'], expected_vt.m)
        self.assertEqual(request_vt['d'], expected_vt.d)
        self.assertEqual(request_vt['o'], expected_vt.o)
        self.assertEqual(request_vt['app_only'], expected_vt.app_only)
        self.assertEqual(request_vt['web_only'], expected_vt.web_only)

    def testPostUpdate(self):
        url = '/api/v1/vartemplate/'
        var_type = self.vartemp1.var_type

        payload = {
            'sg': self.sg1.slug,
            'label': 'Var3',
            'var_type': var_type.slug,
            'lid_hex': '5001',
            'default_input_unit': self.gi.slug,
            'default_output_unit': self.go.slug,
        }

        initial_count = VariableTemplate.objects.count()

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['lid_hex'], '5001')
        self.assertEqual(deserialized['sg'], self.sg1.slug)
        self.assertEqual(deserialized['label'], payload['label'])

        update_payload = {
            'label': 'Var3_updated',
        }
        response = self.client.patch(url+str(deserialized['id'])+'/', data=update_payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        deserialized = json.loads(response.content.decode())
        actual_vartemplate = VariableTemplate.objects.get(id=deserialized['id'])
        self.assertVariableTemplateIsSame(deserialized, actual_vartemplate)
        # self.assertEqual(deserialized['lid_hex'], '5001')
        # self.assertEqual(deserialized['sg'], self.sg1.slug)
        self.assertEqual(deserialized['label'], update_payload['label'])

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.patch(url, data=update_payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testAPIKeyOtherApis(self):
        """
        Ensure that API call fails on non-GET calls of a key/token-enabled API
        """
        var_type = self.vartemp1.var_type

        url = '/api/v1/vartemplate/'
        payload = {
            'sg': self.sg1.slug,
            'created_by': self.u2.slug,
            'label': 'Var3',
            'var_type': var_type.slug,
            'lid_hex': '5001',
            'default_input_unit': self.gi.slug,
            'default_output_unit': self.go.slug
        }

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['lid_hex'], '5001')
        self.assertEqual(deserialized['sg'], self.sg1.slug)

        vartemp_actual = VariableTemplate.objects.get(id=deserialized['id'])
        self.assertEqual(vartemp_actual.created_by.slug, self.u1.slug)

        response = self.client.put(url, data=payload)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        detail_url = '/api/v1/vartemplate/{}/'.format(vartemp_actual.id)
        response = self.client.patch(detail_url, data=payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.delete(detail_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
