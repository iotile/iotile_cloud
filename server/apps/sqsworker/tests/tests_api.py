import json

from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin

from ..pid import ActionPID

user_model = get_user_model()


class ActionPidAPITests(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()

    def tearDown(self):
        self.userTestTearDown()

    def testActionPidUrl(self):
        pid = ActionPID('123456', 'TestAction')
        pid.start()

        url = reverse('api-pid')

        payload = {
            'pid': pid.key
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['pid'], pid.key)
        self.assertTrue('info' in deserialized)
        self.assertEqual(deserialized['info']['type'], 'TestAction')
        self.assertTrue('created_on' in deserialized['info'])

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['pid'], pid.key)
        self.assertTrue('info' in deserialized)

        self.client.logout()

    def testActionPidNotFOundUrl(self):
        pid = ActionPID('123456', 'TestAction')
        pid.start()

        url = reverse('api-pid')

        payload = {
            'pid': 'pid:34567'
        }

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['pid'], payload['pid'])
        self.assertTrue('info' in deserialized)
        self.assertTrue('error' in deserialized['info'])
        self.assertEqual(deserialized['info']['error'], 'Not found')

        self.client.logout()
