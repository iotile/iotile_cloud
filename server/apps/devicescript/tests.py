import json
import datetime
import dateutil.parser
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin

from .models import *

user_model = get_user_model()


class DeviceScriptAPITests(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        DeviceScript.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testSlug(self):
        ds1 = DeviceScript.objects.create(
            name='script 1',
            org=self.o1,
            major_version=2, minor_version=4, patch_version=0,
            created_by=self.u1,
            released=True,
        )
        self.assertEqual(ds1.slug, 'z--0000-0001')

        ds2 = DeviceScript.objects.create(
            name='script 2',
            org=self.o1,
            major_version=2, minor_version=5, patch_version=0,
            created_by=self.u1,
            released=False,
        )
        self.assertEqual(ds2.slug, 'z--0000-0002')

        ds1.delete()
        ds3 = DeviceScript.objects.create(
            name='script 3',
            org=self.o1,
            major_version=2, minor_version=6, patch_version=0,
            created_by=self.u1,
            released=False,
        )
        self.assertEqual(ds3.slug, 'z--0000-0003')


    def testGetList(self):

        url = reverse('devicescript-list')

        ds1 = DeviceScript.objects.create(
            name='script 1',
            org=self.o1,
            major_version=2, minor_version=4, patch_version=0,
            created_by=self.u1,
            released=True,
        )

        DeviceScript.objects.create(
            name='script 1',
            org=self.o1,
            major_version=2, minor_version=5, patch_version=0,
            created_by=self.u1,
            released=False,
        )

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        response = self.client.get(url+'?version=2.4.0&org={0}'.format(str(self.o1.slug)), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.get(url+'?version=2&org={0}'.format(str(self.o1.slug)), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url+'?version=2.4.0', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url+'?version=2', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        self.client.logout()

    def testGetDetail(self):

        f1 = DeviceScript.objects.create(
            name='Script 1',
            org=self.o1,
            major_version=2, minor_version=4, patch_version=0,
            created_by=self.u1,
            released=True,
        )

        f2 = DeviceScript.objects.create(
            name='Script 1',
            org=self.o1,
            major_version=2, minor_version=5, patch_version=0,
            created_by=self.u1,
            released=False,
        )

        url1 = reverse('devicescript-detail', kwargs={'slug': f1.slug})
        url2 = reverse('devicescript-detail', kwargs={'slug': f2.slug})

        response = self.client.get(url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(url2, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(url2, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

    def testGetFile(self):

        f1 = DeviceScript.objects.create(
            name = 'script 1',
            org=self.o1,
            major_version=2, minor_version=4, patch_version=0,
            created_by=self.u1,
            released=True,
        )

        f2 = DeviceScript.objects.create(
            name='script 1',
            org=self.o1,
            major_version=2, minor_version=5, patch_version=0,
            created_by=self.u1,
            released=False,
        )

        url1 = reverse('devicescript-file', kwargs={'slug': f1.slug})
        url2 = reverse('devicescript-file', kwargs={'slug': f2.slug})

        response = self.client.get(url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(url2, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(url2, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

    def testS3FileAttachUrl(self):
        """
        Ensure we can create a new s3file with the script
        """
        f1 = DeviceScript.objects.create(
            name = 'script 1',
            org=self.o1,
            major_version=2, minor_version=4, patch_version=0,
            created_by=self.u1,
            released=True,
        )
        url = reverse('devicescript-uploadurl', kwargs={'slug': f1.slug})

        payload = {
            'name': 'deleteme.trub'
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.o1.has_permission(self.u1, 'can_manage_ota'))

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(DeviceScript.objects.count(), 1)
        self.assertEqual(S3File.objects.count(), 0)
        deserialized = json.loads(response.content.decode())
        self.assertTrue('url' in deserialized)
        self.assertTrue('uuid' in deserialized)
        self.assertTrue('fields' in deserialized)
        self.assertTrue('acl' in deserialized['fields'])
        self.assertEqual(deserialized['fields']['acl'], 'private')

        """
        import os
        import requests
        test_filename = __file__
        self.assertTrue(os.path.isfile(test_filename))
        with open(test_filename, 'r') as fp:
            files = {"file": fp}
            response = requests.post(deserialized["url"], data=deserialized["fields"], files=files)
            print(response)

        self.client.logout()
        """

    def testS3FileAttachSuccess(self):
        """
        Ensure we can create a new s3file with the script
        """
        f1 = DeviceScript.objects.create(
            name = 'script 1',
            org=self.o1,
            major_version=2, minor_version=4, patch_version=0,
            created_by=self.u1,
            released=True,
        )
        url = reverse('devicescript-uploadsuccess', kwargs={'slug': f1.slug})

        payload = {
            'name': 'deleteme.png',
            'uuid': 'a470cd29-915f-4cfb-97de-ea378c46d51c'
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(DeviceScript.objects.count(), 1)
        self.assertEqual(S3File.objects.count(), 1)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['id'], payload['uuid'])

        self.client.logout()
