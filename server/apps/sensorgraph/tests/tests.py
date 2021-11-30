from django.contrib.auth import get_user_model
from django.test import TestCase

from rest_framework import status
from rest_framework.reverse import reverse

from apps.property.models import GenericPropertyOrgEnum, GenericPropertyOrgTemplate
from apps.utils.test_util import TestMixin

from ..models import SensorGraph

user_model = get_user_model()

class SensorGraphTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.projectTemplateTestSetup()

    def tearDown(self):
        GenericPropertyOrgTemplate.objects.all().delete()
        GenericPropertyOrgEnum.objects.all().delete()
        self.projectTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasicSGObject(self):
        t1 = SensorGraph.objects.create(name='SG 1',
                                        major_version=1,
                                        app_tag=2050, app_major_version=2, app_minor_version=1,
                                        created_by=self.u2, org=self.o1)
        self.assertEqual(str(t1), 'SG 1 (v1.0.0)')
        self.assertEqual(t1.slug, 'sg-1-v1-0-0')
        self.assertEqual(t1.app_tag_and_version, '2050 v2.1')

    def testManagerCreate(self):
        s1 = SensorGraph.objects.create_graph(name='SG 1',
                                              created_by=self.u2, org=self.o2)
        self.assertIsNotNone(s1)
        self.assertEqual(s1.name, 'SG 1')
        self.assertEqual(SensorGraph.objects.count(), 1)

        s2 = SensorGraph.objects.create_graph(name='SG 2',
                                              created_by=self.u2, org=self.o2)
        self.assertIsNotNone(s2)
        self.assertEqual(SensorGraph.objects.count(), 2)

    def testObjectAccess(self):
        s1 = SensorGraph.objects.create_graph(name='SG 1',
                                              created_by=self.u2, org=self.o2)
        s2 = SensorGraph.objects.create_graph(name='SG 2',
                                              active=False,
                                              created_by=self.u3, org=self.o3)
        self.assertTrue(s1.has_access(self.u1))
        self.assertTrue(s1.has_access(self.u2))
        self.assertFalse(s1.has_access(self.u3))
        self.assertTrue(s2.has_access(self.u1))
        self.assertFalse(s2.has_access(self.u2))
        self.assertTrue(s2.has_access(self.u3))

    def testBasicGet(self):
        s1 = SensorGraph.objects.create_graph(name='SG 1', app_tag=1,
                                              created_by=self.u2, org=self.o2)
        s2 = SensorGraph.objects.create_graph(name='SG 2',
                                              created_by=self.u2, org=self.o2)
        s3 = SensorGraph.objects.create_graph(name='SG 3', active=False,
                                              created_by=self.u2, org=self.o2)
        s4 = SensorGraph.objects.create_graph(name='SG 4',
                                              active=False,
                                              created_by=self.u3, org=self.o3)
        self.assertFalse(self.o3.is_member(self.u2))

        url_detail1 = reverse('sensor-graph:detail', kwargs={'slug': s1.slug})
        url_detail3 = reverse('sensor-graph:detail', kwargs={'slug': s3.slug})
        url_detail4 = reverse('sensor-graph:detail', kwargs={'slug': s4.slug})

        resp = self.client.get(url_detail1, format='json')
        self.assertRedirects(resp, expected_url='/account/login/?next='+url_detail1, status_code=302, target_status_code=200)

        ok = self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(url_detail1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(url_detail3, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(url_detail4, format='json')
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
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.get(url_detail4, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

        s4.active = True
        s4.save()
        ok = self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(url_detail4, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()
