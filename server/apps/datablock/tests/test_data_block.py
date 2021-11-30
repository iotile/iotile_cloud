import datetime
import json

import dateutil.parser

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from rest_framework import status
from rest_framework.reverse import reverse as api_reverse

from apps.report.models import GeneratedUserReport
from apps.streamfilter.models import *
from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()


class DataBlockTests(TestMixin, TestCase):

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
        self.pd3 = Device.objects.create_device(project=self.p2, label='d3', template=self.dt1, created_by=self.u3)
        StreamId.objects.create_after_new_device(self.pd1)
        StreamId.objects.create_after_new_device(self.pd2)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()
        self.s2 = StreamId.objects.filter(variable=self.v2).first()

    def tearDown(self):
        StreamFilterAction.objects.all().delete()
        StreamFilterTrigger.objects.all().delete()
        StreamFilter.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasic(self):
        db1 = DataBlock.objects.create(org=self.o1, title='test', device=self.pd1, block=1, created_by=self.u1)
        self.assertEqual(self.pd1.slug, 'd--{0}'.format(int2did(self.pd1.id)))
        self.assertEqual(db1.slug, 'b--{0}-{1}'.format(int2bid(db1.block), int2did_short(self.pd1.id)))

        a_stream_slug = db1.get_stream_slug_for('9999')
        self.assertEqual(str(a_stream_slug), 's--0000-0000--{0}--9999'.format(db1.formatted_gid))

    def testAccess(self):
        db1 = DataBlock.objects.create(org=self.o2, title='test', device=self.pd1, block=1, created_by=self.u2)
        self.assertTrue(db1.has_access(self.u1))
        self.assertTrue(db1.has_access(self.u2))
        self.assertFalse(db1.has_access(self.u3))

    def testMemberPermissions(self):
        """
        Test permissions
        """
        db1 = DataBlock.objects.create(org=self.o2, title='test', device=self.pd1, block=1, created_by=self.u1)

        list_url = reverse('org:datablock:list', kwargs={'org_slug': self.o2.slug})
        detail_url = reverse('org:datablock:detail', kwargs={'org_slug': self.o2.slug, 'slug': db1.slug})
        create_url = reverse('org:datablock:add', kwargs={'org_slug': self.o2.slug, 'device_slug': self.pd1.slug})

        self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(self.o2.is_member(self.u2))

        resp = self.client.get(list_url)
        self.assertContains(resp, 'List of data blocks', status_code=200)
        resp = self.client.get(detail_url)
        self.assertContains(resp, 'Block Details', status_code=200)

        payload = {'title': 'A new Archive', 'description': 'foo'}
        resp = self.client.get(create_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.post(create_url, payload)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(DataBlock.objects.count(), 2)

        self.client.logout()

        self.client.login(email='user3@foo.com', password='pass')
        self.assertFalse(self.o2.is_member(self.u3))

        resp = self.client.get(list_url)
        self.assertContains(resp, 'Contact your Organization Administrator for access to this page.', status_code=200)
        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        payload = {'title': 'Not a member', 'description': 'foo'}
        resp = self.client.get(create_url)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        resp = self.client.post(create_url, payload)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(DataBlock.objects.count(), 2)

        self.p1.org.register_user(self.u3, role='r1')
        self.assertFalse(self.p1.org.has_permission(self.u3, 'can_access_datablock'))
        self.assertFalse(self.p1.org.has_permission(self.u3, 'can_create_datablock'))

        resp = self.client.get(list_url, format='json')
        self.assertContains(resp, 'Contact your Organization Administrator for access to this page.', status_code=200)
        resp = self.client.get(detail_url, format='json')
        self.assertContains(resp, 'Contact your Organization Administrator for access to this page.', status_code=200)

        payload = {'title': 'Operator not allowed'}
        resp = self.client.get(create_url)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        resp = self.client.post(create_url, payload)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(DataBlock.objects.count(), 2)

        self.client.logout()

    def testDataBlockListView(self):
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)
        url = reverse('org:datablock:list', args=(self.o3.slug,))

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        db1 = DataBlock.objects.create(org=self.o2, title='test', device=self.pd1, block=1, created_by=self.u2)
        db2 = DataBlock.objects.create(org=self.o3, title='test', device=self.pd2, block=2, created_by=self.u2)
        db3 = DataBlock.objects.create(org=self.o3, title='test', device=self.pd3, block=3, created_by=self.u2)
        db4 = DataBlock.objects.create(org=self.o3, title='test', device=self.pd3, block=4, created_by=self.u2)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.context.get('api'), api_reverse('datablock-datatable') + '?org={}'.format(self.o3.slug))

        resp = self.client.get(url+'?device={}'.format(self.pd2.slug))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.context.get('api'), api_reverse('datablock-datatable') + '?org={}&device={}'.format(self.o3.slug, self.pd2.slug))

    def testDataBlockDetailView(self):
        db1 = DataBlock.objects.create(org=self.o2, title='test', device=self.pd1, block=1, created_by=self.u2)
        user_report = GeneratedUserReport.objects.create(
            org=self.o2,
            label='My report 1',
            source_ref=self.pd1.slug,
            created_by=self.u2
        )
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)
        url = reverse('org:datablock:detail', args=(self.o3.slug, db1.slug))
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
