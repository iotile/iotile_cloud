import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from rest_framework import status

from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()

class GeneratedUserReportTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        GeneratedUserReport.objects.all().defer()
        UserReport.objects.all().defer()
        self.orgTestTearDown()
        self.userTestTearDown()
        self.deviceTemplateTestTearDown()

    def testBasics(self):
        rpt = UserReport.objects.create(label='RPT1', org=self.o2, created_by=self.u2)

        generated = GeneratedUserReport.objects.create(
            report=rpt,
            org=self.o2,
            label='My report',
            source_ref='d--0000-0000-0000-0001',
            created_by=self.u2
        )
        self.assertIsNotNone(generated.id)
        self.assertIsNotNone(generated.created_on)
        self.assertEqual(str(generated), str(generated.label))
        self.assertFalse(generated.public)

    def testViews(self):
        """
        Test view access
        """
        rpt = UserReport.objects.create(label='RPT1', org=self.o2, created_by=self.u2)

        generated = GeneratedUserReport.objects.create(
            report=rpt,
            org=self.o2,
            label='My report',
            source_ref='d--0000-0000-0000-0001',
            created_by=self.u2
        )

        detail_url = generated.get_absolute_url()
        edit_url = generated.get_edit_url()
        delete_url = generated.get_delete_url()

        for url in [detail_url, edit_url, delete_url]:
            resp = self.client.get(url, format='json')
            self.assertRedirects(resp, expected_url='/account/login/?next='+url, status_code=302, target_status_code=200)

        self.client.login(email='user3@foo.com', password='pass')

        for url in [detail_url, edit_url, delete_url]:
            resp = self.client.get(url, format='json')
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, url)

        self.client.logout()
        self.client.login(email='user2@foo.com', password='pass')

        for url in [detail_url, edit_url, delete_url]:
            resp = self.client.get(url, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()


