import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin

from .models import S3File
from .utils import *

user_model = get_user_model()


class FleetAPITests(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()

    def tearDown(self):
        S3File.objects.all().delete()
        self.userTestTearDown()

    def testManager(self):
        self.assertEqual(S3File.objects.count(), 0)
        g1 = S3File.objects.create_file(
            uuid='00000000-23d1-4980-a356-af827e9907a1',
            name='c.txt',
            key='a/b/c.txt',
            user=self.u2
        )
        self.assertEqual(S3File.objects.count(), 1)
        self.assertEqual(str(g1.id), '00000000-23d1-4980-a356-af827e9907a1')
        self.assertEqual(g1.title, 'c.txt')
        self.assertEqual(g1.key, 'a/b/c.txt')
        self.assertEqual(g1.created_by, self.u2)
        self.assertEqual(g1.bucket, settings.S3FILE_BUCKET_NAME)

        g2 = S3File.objects.set_or_create_file(
            uuid='00000000-23d1-4980-a356-af827e9907a1',
            name='d.txt',
            key='a/b/d.txt',
            user=self.u2
        )
        self.assertEqual(S3File.objects.count(), 1)
        self.assertEqual(str(g2.id), '00000000-23d1-4980-a356-af827e9907a1')
        self.assertEqual(g2.title, 'd.txt')
        self.assertEqual(g2.key, 'a/b/d.txt')
        self.assertEqual(g2.created_by, self.u2)
        self.assertEqual(g2.bucket, settings.S3FILE_BUCKET_NAME)

        g3 = S3File.objects.set_or_create_file(
            uuid='11111111-23d1-4980-a356-af827e9907a1',
            name='e.txt',
            key='a/b/e.txt',
            user=self.u2
        )
        self.assertEqual(S3File.objects.count(), 2)
        self.assertEqual(str(g3.id), '11111111-23d1-4980-a356-af827e9907a1')
        self.assertEqual(g3.title, 'e.txt')
        self.assertEqual(g3.key, 'a/b/e.txt')
        self.assertEqual(g3.created_by, self.u2)
        self.assertEqual(g3.bucket, settings.S3FILE_BUCKET_NAME)

    def testGetContentType(self):
        self.assertEqual(get_content_type('foo'), 'text/plain')
        self.assertEqual(get_content_type('index.html'), 'text/html')
        self.assertEqual(get_content_type('index.HTML'), 'text/html')
        self.assertEqual(get_content_type('image.PNG'), 'image/png')
        self.assertEqual(get_content_type('image.jpg'), 'image/jpeg')
        self.assertEqual(get_content_type('file.jsonp'), 'application/javascript')
        self.assertEqual(get_content_type('file.json'), 'application/json')
        self.assertEqual(get_content_type('file.zip'), 'application/zip')

    def testSign(self):
        """
        Ensure we can create a new Org object.
        """
        url = reverse('api-s3file-sign')

        data = {
            'expiration': '2018-03-19T05:10:42.585Z',
            'conditions': [
                {
                    'acl': 'public-read'
                }, {
                    'bucket': 'iotile-cloud-media'
                }, {
                    'Content-Type': 'image/png'
                }, {
                    'success_action_status': '200'
                }, {
                    'key': 'dev/incoming/a470cd29-915f-4cfb-97de-ea378c46d51c/original.png'
                }, {
                    'x-amz-meta-qqfilename': 'image001.png'
                },
                ['content-length-range', '0', '4096000']
            ]
        }

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testPostUrl(self):
        from apps.utils.aws.s3 import get_s3_post_url
        fields = {
            'acl': 'private',
            'x-amz-meta-filename': 'tests.py',
            'x-amz-meta-uuid': 'a470cd29-915f-4cfb-97de-ea378c46d51c',
            'x-amz-meta-type': 'note',
            'Content-Type': 'text/plain',
        }

        post = get_s3_post_url(
            bucket_name='iotile-cloud-media',
            key_name='dev/s3file/deleteme/tests.py',
            max_length=4096000,
            fields=fields
        )
        self.assertTrue('url' in post)
        self.assertTrue('fields' in post)
        for key in fields.keys():
            self.assertTrue(key in post['fields'], key)
            self.assertEqual(post['fields'][key], fields[key], key)

        """
        import requests
        import os
        module_path = os.path.dirname(__file__)
        test_filename = os.path.join(module_path, 'tests.py')
        self.assertTrue(os.path.isfile(test_filename))
        with open(test_filename, 'r') as fp:
            files = {"file": fp}
            response = requests.post(post["url"], data=post["fields"], files=files)
            print(response)
        """
