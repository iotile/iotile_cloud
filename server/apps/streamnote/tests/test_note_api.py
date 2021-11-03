import json

from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from apps.streamfilter.models import *
from apps.utils.test_util import TestMixin
from apps.vartype.models import VarType

from ..models import *

user_model = get_user_model()


class StreamNoteAPITests(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=1,
        )
        self.v2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p2, created_by=self.u3, lid=2,
        )
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)
        StreamId.objects.create_after_new_device(self.pd1)
        StreamId.objects.create_after_new_device(self.pd2)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()
        self.s2 = StreamId.objects.filter(variable=self.v2).first()
        self.var_type = VarType.objects.create(
            name='Accelerometer',
            storage_units_full='Object',
            created_by=self.u1
        )

        if cache:
            cache.clear()

    def tearDown(self):
        S3File.objects.all().delete()
        StreamNote.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasicGet(self):
        n1 = StreamNote.objects.create(
            target_slug=self.s1.slug, timestamp=timezone.now(), note='Note 1', created_by=self.u2
        )
        n2 = StreamNote.objects.create(
            target_slug=self.pd1.slug, timestamp=timezone.now(), note='Note 2', created_by=self.u1, type='sc'
        )
        list_url = reverse('streamnote-list')
        detail_url1 = reverse('streamnote-detail', kwargs={'pk': n1.id})
        detail_url2 = reverse('streamnote-detail', kwargs={'pk': n2.id})

        response = self.client.get(list_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.get(detail_url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.get(detail_url2, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(list_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.get(list_url+'?target={}'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['note'], 'Note 1')
        self.assertEqual(deserialized['results'][0]['user_info']['slug'], self.u2.slug)
        response = self.client.get(list_url+'?target={}'.format(self.pd1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get(detail_url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['note'], 'Note 1')
        self.assertEqual(deserialized['type'], 'ui')
        self.assertEqual(deserialized['user_info']['slug'], self.u2.slug)
        response = self.client.get(detail_url2, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['note'], 'Note 2')
        self.assertEqual(deserialized['type'], 'sc')
        self.assertEqual(deserialized['user_info']['slug'], self.u1.slug)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.o2.has_permission(self.u2, 'can_read_notes'))

        response = self.client.get(list_url+'?target={}'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        response = self.client.get(detail_url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['note'], 'Note 1')
        self.assertEqual(deserialized['user_info']['slug'], self.u2.slug)
        response = self.client.get(detail_url2, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(list_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.get(detail_url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.get(detail_url2, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        membership = self.p1.org.register_user(self.u3, role='m1')
        membership.permissions['can_read_notes'] = False
        membership.save()

        response = self.client.get(list_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.get(detail_url2, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testGetLastN(self):
        n1 = StreamNote.objects.create(
            target_slug=self.pd1.slug, timestamp=timezone.now(), note='Note 1', created_by=self.u2
        )
        n2 = StreamNote.objects.create(
            target_slug=self.pd1.slug, timestamp=timezone.now(), note='Note 2', created_by=self.u1, type='sc'
        )
        n3 = StreamNote.objects.create(
            target_slug=self.pd1.slug, timestamp=timezone.now(), note='Note 3', created_by=self.u1, type='sc'
        )
        url = reverse('streamnote-list')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url+'?target={}'.format(self.pd1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)
        self.assertEqual(deserialized['results'][0]['note'], 'Note 1')

        response = self.client.get(url+'?target={}&lastn=1'.format(self.pd1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['note'], 'Note 3')

        response = self.client.get(url+'?target={}&lastn=2'.format(self.pd1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)
        self.assertEqual(deserialized['results'][0]['note'], 'Note 2')
        self.assertEqual(deserialized['results'][1]['note'], 'Note 3')

        response = self.client.get(url+'?target={}&lastn=-1'.format(self.pd1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(url+'?target={}&lastn=20000000000'.format(self.pd1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.logout()

    def testGetWithFilter(self):
        n1 = StreamNote.objects.create(
            target_slug=self.pd1.slug, timestamp=timezone.now(), note='Note 1', created_by=self.u2
        )
        n2 = StreamNote.objects.create(
            target_slug=self.pd1.slug, timestamp=timezone.now(), note='Note 2', created_by=self.u1, type='sc'
        )
        n3 = StreamNote.objects.create(
            target_slug=self.pd1.slug, timestamp=timezone.now(), note='Note 3', created_by=self.u1, type='sc'
        )
        n4 = StreamNote.objects.create(
            target_slug=self.pd1.slug, timestamp=timezone.now(), note='Note 4', created_by=self.u1, type='sc'
        )
        n5 = StreamNote.objects.create(
            target_slug=self.s1.slug, timestamp=timezone.now(), note='Note 5', created_by=self.u1, type='sc'
        )
        url = reverse('streamnote-list')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(url+'?target={}'.format(self.pd1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 4)

        response = self.client.get(url+'?target={}'.format(self.s1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.get(url+'?target={0}&id_min={1}'.format(self.pd1.slug, n1.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 4)

        response = self.client.get(url+'?target={0}&id_min={1}&id_max={1}'.format(self.pd1.slug, n1.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

    def testBasicPost(self):
        url = reverse('streamnote-list')
        payload = {
            'target': self.s1.slug,
            'timestamp': timezone.now(),
            'note': 'This is my first node'
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
        self.assertEqual(StreamNote.objects.count(), 1)
        deserialized = json.loads(response.content.decode())
        self.assertTrue('id' in deserialized)
        self.assertEqual(deserialized['target'], self.s1.slug)
        self.assertTrue('user_info' in deserialized)
        self.assertEqual(deserialized['user_info']['slug'], self.u1.slug)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            'target': self.s1.slug,
            'timestamp': timezone.now(),
            'note': 'This is my second node'
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamNote.objects.count(), 2)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['target'], self.s1.slug)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.p1.org.register_user(self.u3, role='r1')

        payload = {
            'target': self.s1.slug,
            'timestamp': timezone.now(),
            'note': 'This is my third node (operator)'
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamNote.objects.count(), 3)

        self.client.logout()

    def testMultiPost(self):
        url = reverse('streamnote-list')
        payload = [
            {
                'target': self.s1.slug,
                'timestamp': timezone.now(),
                'note': 'This is my first node'
            },
            {
                'target': self.s1.slug,
                'timestamp': timezone.now(),
                'note': 'This is my second node'
            }
        ]

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamNote.objects.count(), 2)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        self.client.logout()

    def testS3FileAttachUrl(self):
        """
        Ensure we can create a new s3file with the script
        """
        n1 = StreamNote.objects.create(
            target_slug=self.s1.slug, timestamp=timezone.now(), note='Note 1', created_by=self.u2
        )
        url = reverse('streamnote-uploadurl', kwargs={'pk': n1.pk})

        payload = {
            'name': 'deleteme.png'
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(StreamNote.objects.count(), 1)
        self.assertEqual(S3File.objects.count(), 0)
        deserialized = json.loads(response.content.decode())
        self.assertTrue('url' in deserialized)
        self.assertTrue('uuid' in deserialized)
        self.assertTrue('fields' in deserialized)
        self.assertTrue('acl' in deserialized['fields'])
        self.assertEqual(deserialized['fields']['acl'], 'private')
        self.assertEqual(deserialized['fields']['x-amz-meta-filename'], 'deleteme.png')
        self.assertEqual(deserialized['fields']['x-amz-meta-type'], 'note')

        """
        import os
        import requests
        test_filename = __file__
        self.assertTrue(os.path.isfile(test_filename))
        with open(test_filename, 'r') as fp:
            files = {"file": fp}
            response = requests.post(deserialized["url"], data=deserialized["fields"], files=files)
            print(response)
        """

        self.client.logout()

    def testS3FileAttachSuccess(self):
        """
        Ensure we can create a new s3file with the script
        """
        n1 = StreamNote.objects.create(
            target_slug=self.s1.slug, timestamp=timezone.now(), note='Note 1', created_by=self.u2
        )
        url = reverse('streamnote-uploadsuccess', kwargs={'pk': n1.pk})

        payload = {
            'name': 'deleteme.png',
            'uuid': 'a470cd29-915f-4cfb-97de-ea378c46d51c'
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(StreamNote.objects.count(), 1)
        self.assertEqual(S3File.objects.count(), 1)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['id'], payload['uuid'])

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.p1.org.register_user(self.u3, role='r1')

        payload = {
            'name': 'deleteme.png',
            'uuid': 'a470cd29-915f-0000-97de-ea378c461234'
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(S3File.objects.count(), 2)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['id'], payload['uuid'])

        self.client.logout()



