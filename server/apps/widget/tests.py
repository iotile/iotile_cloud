
import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin

from apps.stream.models import *
from apps.streamdata.models import StreamData

from .models import *

user_model = get_user_model()

class WidgetTestCase(TestMixin, TestCase):
    """
    Fixure includes:
    """
    #fixtures = ['testdb_main.json']

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
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1',
                                                template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p2, label='d2',
                                                template=self.dt1, created_by=self.u3)
        self.s1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=self.pd1, created_by=self.u2
        )

    def tearDown(self):
        StreamData.objects.all().delete()
        WidgetInstance.objects.all().delete()
        WidgetTemplate.objects.all().delete()
        PageTemplate.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasicPageObjects(self):
        p = PageTemplate.objects.create(label='P2', template_path='/foo', created_by=self.u1)
        self.assertEqual(str(p), 'P2')
        self.assertEqual(p.get_html_template(), '/foo/page.html')

    def testBasicWidgetObjects(self):
        t = WidgetTemplate.objects.create(template_path='/foo', label='T1', created_by=self.u1)
        self.assertEqual(str(t), 'T1')
        self.assertEqual(t.get_html_template(), '/foo/widget.html')
        self.assertEqual(t.get_js_template(), '/foo/script.js')

    def testBasicInstanceObjects(self):
        p = PageTemplate.objects.create(label='P2', template_path='/foo', created_by=self.u1)
        t = WidgetTemplate.objects.create(template_path='/foo', created_by=self.u1)
        i = WidgetInstance.objects.create(widget_definition=t, page_definition=p, primary_lid=400,
                                          label='I1', created_by=self.u1)
        self.assertEqual(str(i), 'I1')
        self.assertEqual(i.primary_variable_id_in_hex, '0190')

    def testBasicPages(self):
        """
        Ensure we can call GET old device page
        """

        d1_url = reverse('org:page:device', kwargs={'org_slug': self.pd1.org.slug, 'slug': self.pd1.slug})
        d2_url = reverse('org:page:device', kwargs={'org_slug': self.pd2.org.slug, 'slug': self.pd2.slug})

        resp = self.client.get(d1_url, format='json')
        self.assertRedirects(resp, expected_url='/account/login/?next='+d1_url, status_code=302, target_status_code=200)
        resp = self.client.get(d2_url, format='json')
        self.assertRedirects(resp, expected_url='/account/login/?next='+d2_url, status_code=302, target_status_code=200)

        self.client.login(email='user1@foo.com', password='pass')

        resp = self.client.get(d1_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(d2_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

        self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(d1_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(d2_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.get(d1_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.get(d2_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

