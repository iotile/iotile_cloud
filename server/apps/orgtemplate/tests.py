import json
import datetime
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin

from .models import *

user_model = get_user_model()

class OrgTemplateTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()

    def tearDown(self):
        self.projectTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasicOrgObject(self):
        t1 = OrgTemplate.objects.create(name='Org 1',
                                        major_version=1,
                                        created_by=self.u2)
        self.assertEqual(str(t1), 'Org 1 - v1.0.0')
        self.assertEqual(t1.slug, 'org-1-v1-0-0')

    def testManagerCreate(self):
        t1 = OrgTemplate.objects.create_template(name='Master Org 1',
                                                 created_by=self.u2)
        self.assertIsNotNone(t1)
        self.assertEqual(t1.name, 'Master Org 1')
        self.assertEqual(OrgTemplate.objects.count(), 1)

        t2 = OrgTemplate.objects.create_template(name='Template 2',
                                                 created_by=self.u2)
        self.assertIsNotNone(t2)
        self.assertEqual(OrgTemplate.objects.count(), 2)

    def testObjectAccess(self):
        t1 = OrgTemplate.objects.create_template(name='Master Org 1',
                                                 created_by=self.u2)
        t2 = OrgTemplate.objects.create_template(name='Master Org 2',
                                                 active=False,
                                                 created_by=self.u3)
        self.assertTrue(t1.has_access(self.u1))
        self.assertTrue(t1.has_access(self.u2))
        self.assertFalse(t1.has_access(self.u3))
        self.assertTrue(t2.has_access(self.u1))
        self.assertFalse(t2.has_access(self.u2))
        self.assertTrue(t2.has_access(self.u3))

    def testBasicOrgGet(self):
        t1 = OrgTemplate.objects.create_template(name='Master Org 1',
                                                 created_by=self.u2)
        t2 = OrgTemplate.objects.create_template(name='Master Org 2',
                                                 created_by=self.u2)
        t3 = OrgTemplate.objects.create_template(name='Master Org 3',
                                                 active=False,
                                                 created_by=self.u3)
        self.assertFalse(self.o3.is_member(self.u2))

        url_detail1 = reverse('org-template:detail', kwargs={'slug': t1.slug})
        url_detail3 = reverse('org-template:detail', kwargs={'slug': t3.slug})

        resp = self.client.get(url_detail1, format='json')
        self.assertRedirects(resp, expected_url='/account/login/?next='+url_detail1, status_code=302, target_status_code=200)

        ok = self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(url_detail1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(url_detail3, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        ok = self.client.login(email='user1@foo.com', password='pass')

        resp = self.client.get(url_detail1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(url_detail3, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.get(url_detail1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.get(url_detail3, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

        t3.active = True
        t3.save()
        ok = self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(url_detail3, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

class OrgTemplateAPITestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()

    def tearDown(self):
        self.projectTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testGet(self):
        url = '/api/v1/ot/'
        t1 = OrgTemplate.objects.create(name='Org 1',
                                            major_version=1,
                                            created_by=self.u2)
        t2 = OrgTemplate.objects.create(name='Org 2',
                                            major_version=1,
                                            created_by=self.u2)
        url_detail = '/api/v1/ot/{}/'.format(t1.slug)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(url_detail, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(url_detail, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(url_detail, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testPost(self):
        url = '/api/v1/ot/'
        payload = {
            'name': 'foo'
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()


    def testPostWithExtraData(self):
        url = '/api/v1/ot/'
        payload = {
            'name': 'bar',
            'extra_data': {
                'web': {
                    'orgTemplateSlug': 'shipping'
                }
            }
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        pt = OrgTemplate.objects.first()
        self.assertTrue('web' in pt.extra_data)
        self.assertTrue('orgTemplateSlug' in pt.extra_data['web'])
        self.assertEqual(pt.extra_data['web']['orgTemplateSlug'], 'shipping')

        payload = {
            'extra_data': {
                'web': {
                    'orgTemplateSlug': 'default'
                }
            }
        }

        url = '/api/v1/ot/{}/'.format(pt.slug)
        response = self.client.patch(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        pt = OrgTemplate.objects.first()
        self.assertTrue('web' in pt.extra_data)
        self.assertTrue('orgTemplateSlug' in pt.extra_data['web'])
        self.assertEqual(pt.extra_data['web']['orgTemplateSlug'], 'default')

        self.client.logout()

