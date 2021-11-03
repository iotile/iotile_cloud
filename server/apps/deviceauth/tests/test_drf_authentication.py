import json

from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin

from ..models import *
from ..authentication import *

user_model = get_user_model()


class MainTestCase(TestMixin, APITestCase):
    """
    Fixure includes:
    """
    #fixtures = ['testdb_main.json']

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        DeviceKey.objects.all().delete()
        Device.objects.all().delete()
        self.orgTestTearDown()
        self.userTestTearDown()
        self.deviceTemplateTestTearDown()

    def test_token_access(self):

        d1 = Device.objects.create(id=1, project=self.p1, template=self.dt1,
                                   created_by=self.u2, claimed_by=self.u2)
        u4 = user_model.objects.create_user(username='User4', email='user4@foo.com', password='pass')
        u4.is_active = True
        u4.save()

        token = encode_device_ajwt_key(user=u4, device=d1)

        client = APIClient()

        client.credentials(HTTP_AUTHORIZATION='a-jwt ' + 'foo')
        detail_url1 = reverse('device-detail', kwargs={'slug': str(d1.slug)})
        resp = client.get(detail_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        client.credentials(HTTP_AUTHORIZATION='a-jwt ' + str(token.decode()))
        detail_url1 = reverse('device-detail', kwargs={'slug': str(d1.slug)})
        resp = client.get(detail_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        token = encode_device_ajwt_key(user=self.u2, device=d1)
        client.credentials(HTTP_AUTHORIZATION='a-jwt ' + str(token.decode()))
        detail_url1 = reverse('device-detail', kwargs={'slug': str(d1.slug)})
        resp = client.get(detail_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_token_api(self):

        d1 = Device.objects.create(id=1, project=self.p1, template=self.dt1,
                                   created_by=self.u2, claimed_by=self.u2)
        u4 = user_model.objects.create_user(username='User4', email='user4@foo.com', password='pass')
        u4.is_active = True
        u4.save()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        key_url = reverse('device-key', kwargs={'slug': str(d1.slug)})+'?type=a-jwt'
        resp = self.client.get(key_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        key = deserialized['key']

        self.client.logout()

        client = APIClient()

        client.credentials(HTTP_AUTHORIZATION='a-jwt ' + key)
        info_url = reverse('api-user-info')
        resp = client.get(info_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], d1.claimed_by.slug)
        self.assertNotEqual(deserialized['jwt'], key)

        device_url = reverse('device-detail', kwargs={'slug': str(d1.slug)})
        resp = client.get(device_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_secrecy(self):
        """
        Ensure the 'A-JWT-KEY' is not downloadable
        """

        d1 = Device.objects.create(id=1, project=self.p1, template=self.dt1,
                                   created_by=self.u2, claimed_by=self.u2)
        u4 = user_model.objects.create_user(username='User4', email='user4@foo.com', password='pass')
        u4.is_active = True
        u4.save()

        DeviceKey.objects.get_or_create_ajwt_device_key(d1)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        key_url = reverse('device-key', kwargs={'slug': str(d1.slug)})+'?type=A-JWT-KEY'
        resp = self.client.get(key_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        key_url = reverse('device-key', kwargs={'slug': str(d1.slug)})+'?type=A-JWT-KEY'
        resp = self.client.get(key_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def test_not_claimed(self):

        d1 = Device.objects.create(id=1, template=self.dt1, created_by=self.u2)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        key_url = reverse('device-key', kwargs={'slug': str(d1.slug)})+'?type=a-jwt'
        resp = self.client.get(key_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()
