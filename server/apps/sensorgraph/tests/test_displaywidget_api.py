import json

from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()

class DisplayWidgetTemplateAPITestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.sg1 = self.createTestSensorGraph()

    def tearDown(self):
        self.sensorGraphTestTearDown()
        self.projectTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def assertDisplayWidgetTemplateIsSame(self, request_widget, expected_widget: DisplayWidgetTemplate):
        self.assertEqual(request_widget['id'], expected_widget.id)
        self.assertEqual(request_widget['label'], expected_widget.label)
        self.assertEqual(request_widget['sg'], expected_widget.sg.slug)
        self.assertEqual(request_widget['lid_hex'], expected_widget.lid_hex)
        if expected_widget.var_type:
            self.assertEqual(request_widget['var_type'], expected_widget.var_type.slug)
        else:
            self.assertEqual(request_widget['var_type'], None)
        self.assertEqual(request_widget['show_in_app'], expected_widget.show_in_app)
        self.assertEqual(request_widget['show_in_web'], expected_widget.show_in_web)
        self.assertEqual(request_widget['type'], expected_widget.type)
        self.assertEqual(request_widget['args'], expected_widget.args)

    def testPostUpdate(self):
        url = '/api/v1/widget/'
        var_type = self.vartemp1.var_type

        payload = {
            'sg': self.sg1.slug,
            'label': 'Widget-to-update',
            'var_type': var_type.slug,
            'lid_hex': '5020',
            'show_in_app': False,
            'show_in_web': True,
        }

        initial_count = DisplayWidgetTemplate.objects.count()

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
        new_widget = json.loads(response.content.decode())
        self.assertEqual(new_widget['lid_hex'], '5020')
        self.assertEqual(new_widget['sg'], self.sg1.slug)
        self.assertEqual(new_widget['label'], payload['label'])

        detail_url = url + str(new_widget['id']) + '/'
        update_payload = {
            'label': 'Widget-updated',
        }
        response = self.client.patch(detail_url, data=update_payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        deserialized = json.loads(response.content.decode())
        actual_widget = DisplayWidgetTemplate.objects.get(id=deserialized['id'])
        self.assertDisplayWidgetTemplateIsSame(deserialized, actual_widget)
        self.assertEqual(deserialized['lid_hex'], '5020')
        self.assertEqual(deserialized['sg'], self.sg1.slug)
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

        url = '/api/v1/widget/'
        payload = {
            'sg': self.sg1.slug,
            'label': 'Var3',
            'lid_hex': '5020',
            'show_in_app': False,
            'show_in_web': True,
        }

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['lid_hex'], '5020')
        self.assertEqual(deserialized['sg'], self.sg1.slug)

        dwt_actual = DisplayWidgetTemplate.objects.get(id=deserialized['id'])
        self.assertEqual(dwt_actual.created_by.slug, self.u1.slug)

        response = self.client.put(url, data=payload)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        detail_url = '/api/v1/widget/{}/'.format(dwt_actual.id)
        response = self.client.patch(detail_url, data=payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.delete(detail_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
