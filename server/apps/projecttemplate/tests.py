import datetime
import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.org.models import Org
from apps.project.models import Project
from apps.utils.test_util import TestMixin

from .models import *

user_model = get_user_model()

class ProjectTemplateTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()

    def tearDown(self):
        self.projectTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasicProjectObject(self):
        t1 = ProjectTemplate.objects.create(name='Project 1',
                                            major_version=1,
                                            created_by=self.u2, org=self.o2)
        self.assertEqual(str(t1), 'Org 1 - Project 1')
        self.assertEqual(t1.slug, 'project-1-v1-0-0')

    def testMasterProject(self):
        t1 = ProjectTemplate.objects.create(name='Master Project 1',
                                            major_version=1,
                                            created_by=self.u2, org=self.o2)
        master_project = Project.objects.all().last()
        self.assertTrue(master_project.is_template)
        self.assertEqual(t1, master_project.project_template)
        t2 = ProjectTemplate.objects.create_template(name='Master Project 2',
                                                     major_version=1,
                                                     created_by=self.u2, org=self.o2)
        master_project = Project.objects.all().order_by('created_on').last()
        self.assertTrue(master_project.is_template)
        self.assertEqual(t2, master_project.project_template)

    def testManagerCreate(self):
        t1 = ProjectTemplate.objects.create_template(name='Master Project 1',
                                                     created_by=self.u2, org=self.o2)
        self.assertIsNotNone(t1)
        self.assertEqual(t1.name, 'Master Project 1')
        self.assertEqual(ProjectTemplate.objects.count(), 1)

        t2 = ProjectTemplate.objects.create_template(name='Template 2',
                                                     created_by=self.u2, org=self.o2)
        self.assertIsNotNone(t2)
        self.assertEqual(ProjectTemplate.objects.count(), 2)

    def testObjectAccess(self):
        t1 = ProjectTemplate.objects.create_template(name='Master Project 1',
                                                     created_by=self.u2, org=self.o2)
        t2 = ProjectTemplate.objects.create_template(name='Master Project 2',
                                                     active=False,
                                                     created_by=self.u3, org=self.o3)
        self.assertTrue(t1.has_access(self.u1))
        self.assertTrue(t1.has_access(self.u2))
        self.assertFalse(t1.has_access(self.u3))
        self.assertTrue(t2.has_access(self.u1))
        self.assertFalse(t2.has_access(self.u2))
        self.assertTrue(t2.has_access(self.u3))

    def testBasicProjectGet(self):
        t1 = ProjectTemplate.objects.create_template(name='Master Project 1',
                                                    created_by=self.u2, org=self.o2)
        t2 = ProjectTemplate.objects.create_template(name='Master Project 2',
                                                    created_by=self.u2, org=self.o2)
        t3 = ProjectTemplate.objects.create_template(name='Master Project 3',
                                                    active=False,
                                                    created_by=self.u3, org=self.o3)
        self.assertFalse(self.o3.is_member(self.u2))

        url_detail1 = reverse('project-template:detail', kwargs={'slug': t1.slug})
        url_detail3 = reverse('project-template:detail', kwargs={'slug': t3.slug})

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

class ProjectTemplateAPITestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()

    def tearDown(self):
        self.projectTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testGet(self):
        url = '/api/v1/pt/'
        t1 = ProjectTemplate.objects.create(name='Project 1',
                                            major_version=1,
                                            created_by=self.u2, org=self.o2)
        t2 = ProjectTemplate.objects.create(name='Project 2',
                                            major_version=1,
                                            created_by=self.u2, org=self.o2)
        url_detail = '/api/v1/pt/{}/'.format(t1.slug)

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
        url = '/api/v1/pt/'
        payload = {
            'name': 'foo',
            'org': str(self.o1.slug)
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
        url = '/api/v1/pt/'
        payload = {
            'name': 'bar',
            'org': str(self.o1.slug),
            'extra_data': {
                'web': {
                    'projectTemplateSlug': 'shipping'
                }
            }
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        pt = ProjectTemplate.objects.first()
        self.assertTrue('web' in pt.extra_data)
        self.assertTrue('projectTemplateSlug' in pt.extra_data['web'])
        self.assertEqual(pt.extra_data['web']['projectTemplateSlug'], 'shipping')

        payload = {
            'extra_data': {
                'web': {
                    'projectTemplateSlug': 'default'
                }
            }
        }

        url = '/api/v1/pt/{}/'.format(pt.slug)
        response = self.client.patch(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        pt = ProjectTemplate.objects.first()
        self.assertTrue('web' in pt.extra_data)
        self.assertTrue('projectTemplateSlug' in pt.extra_data['web'])
        self.assertEqual(pt.extra_data['web']['projectTemplateSlug'], 'default')

        self.client.logout()

