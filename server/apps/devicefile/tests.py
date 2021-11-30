import datetime
import json

import dateutil.parser

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin

from .models import *

user_model = get_user_model()


class DeviceFileAPITests(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        DeviceFile.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testSlug(self):
        ds1 = DeviceFile.objects.create(
            type='os', tag=2055,
            major_version=2, minor_version=4,
            created_by=self.u1,
            released_by=self.o1,
            released=True,
        )
        self.assertEqual(ds1.slug, 'os2055--2-4')
        self.assertEqual(str(ds1), 'os2055:v2.4')

        ds2 = DeviceFile.objects.create(
            type='os', tag=2055,
            major_version=2, minor_version=5,
            created_by=self.u1,
            released_by=self.o1,
            released=False,
        )
        self.assertEqual(ds2.slug, 'os2055--2-5')
        self.assertEqual(str(ds2), 'os2055:v2.5')

    def testPost(self):
        """
        Ensure we can create a new s3file with the script
        """
        url = reverse('devicefile-list')

        payload = {
            'type': 'os',
            'tag': '2070',
            'released_by': self.o1.slug,
            'major_version': 2,
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['slug'], 'os2070--2-0')
        self.assertEqual(deserialized['type'], 'os')
        self.assertEqual(deserialized['notes'], None)
        self.assertEqual(deserialized['released'], False)

        payload = {
            'type': 'foo', # Not supported
            'tag': '2070',
            'released_by': self.o1.slug,
            'major_version': 2,
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.logout()

    def testGetList(self):

        url = reverse('devicefile-list')

        ds1 = DeviceFile.objects.create(
            type='os', tag=2055,
            major_version=2, minor_version=4,
            created_by=self.u1,
            released_by=self.o1,
            released=True,
        )

        DeviceFile.objects.create(
            type='os', tag=2055,
            major_version=2, minor_version=5,
            created_by=self.u1,
            released_by=self.o1,
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

        f1 = DeviceFile.objects.create(
            type='os', tag=2055,
            major_version=2, minor_version=4,
            created_by=self.u1,
            released_by=self.o1,
            released=True,
        )

        f2 = DeviceFile.objects.create(
            type='os', tag=2055,
            major_version=2, minor_version=5,
            created_by=self.u1,
            released_by=self.o1,
            released=False,
        )

        url1 = reverse('devicefile-detail', kwargs={'slug': f1.slug})
        url2 = reverse('devicefile-detail', kwargs={'slug': f2.slug})

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

        f1 = DeviceFile.objects.create(
            type='os', tag=2055,
            major_version=2, minor_version=4,
            created_by=self.u1,
            released_by=self.o1,
            released=True,
        )

        f2 = DeviceFile.objects.create(
            type='os', tag=2055,
            major_version=2, minor_version=5,
            created_by=self.u1,
            released_by=self.o1,
            released=False,
        )

        url1 = reverse('devicefile-file', kwargs={'slug': f1.slug})
        url2 = reverse('devicefile-file', kwargs={'slug': f2.slug})

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
        f1 = DeviceFile.objects.create(
            type='os', tag=2055,
            major_version=2, minor_version=4,
            created_by=self.u1,
            released_by=self.o1,
            released=True,
        )
        url = reverse('devicefile-uploadurl', kwargs={'slug': f1.slug})

        payload = {
            'name': 'deleteme.ship'
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.o1.has_permission(self.u1, 'can_manage_ota'))

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(DeviceFile.objects.count(), 1)
        self.assertEqual(S3File.objects.count(), 0)
        deserialized = json.loads(response.content.decode())
        self.assertTrue('url' in deserialized)
        self.assertTrue('uuid' in deserialized)
        self.assertTrue('fields' in deserialized)
        self.assertTrue('acl' in deserialized['fields'])
        self.assertEqual(deserialized['fields']['acl'], 'private')
        self.assertEqual(deserialized['fields']['x-amz-meta-filename'], 'deleteme.ship')
        self.assertEqual(deserialized['fields']['x-amz-meta-type'], 'script')

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
        f1 = DeviceFile.objects.create(
            type='os', tag=2055,
            major_version=2, minor_version=4,
            created_by=self.u1,
            released_by=self.o1,
            released=True,
        )
        url = reverse('devicefile-uploadsuccess', kwargs={'slug': f1.slug})

        payload = {
            'name': 'deleteme.ship',
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
        self.assertEqual(DeviceFile.objects.count(), 1)
        self.assertEqual(S3File.objects.count(), 1)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['id'], payload['uuid'])

        self.client.logout()

