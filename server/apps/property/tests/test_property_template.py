import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.physicaldevice.models import Device
from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()

class GenericProperyTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        GenericPropertyOrgTemplate.objects.all().delete()
        GenericPropertyOrgEnum.objects.all().delete()
        self.orgTestTearDown()
        self.userTestTearDown()
        self.deviceTemplateTestTearDown()

    def testBasics(self):
        p1 = GenericPropertyOrgTemplate.objects.create(name='F1', org=self.o2, created_by=self.u2, type='enum')
        GenericPropertyOrgEnum.objects.create(value='a', org=self.o2, created_by=self.u2, template=p1)
        GenericPropertyOrgEnum.objects.create(value='b', org=self.o2, created_by=self.u2, template=p1)

        self.assertEqual(p1.get_absolute_url(), '/property/template/{}/{}/'.format(self.o2.slug, p1.id))

    def testPermissions(self):
        """
        Test permissions
        """
        p1 = GenericPropertyOrgTemplate.objects.create(name='F1', org=self.o2, created_by=self.u2, type='enum')
        e1 = GenericPropertyOrgEnum.objects.create(value='a', org=self.o2, created_by=self.u2, template=p1)
        GenericPropertyOrgEnum.objects.create(value='b', org=self.o2, created_by=self.u2, template=p1)

        page_list = [
            reverse('property:template-list', kwargs={'org_slug': self.o2.slug}),
            reverse('property:template-detail', kwargs={'org_slug': self.o2.slug, 'pk': p1.id}),
            reverse('property:template-enum-add', kwargs={'org_slug': self.o2.slug}),
            reverse('property:template-enum-delete', kwargs={
                'org_slug': self.o2.slug, 'template_pk': p1.id, 'pk': e1.id
            }),
        ]

        for page in page_list:
            resp = self.client.get(page)
            self.assertEqual(resp.status_code, 302)

        self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(self.o2.is_member(self.u2))
        self.assertTrue(self.o2.has_permission(self.u2, 'can_delete_org'))

        for page in page_list:
            resp = self.client.get(page)
            self.assertEqual(resp.status_code, 200)

        self.client.logout()

        self.client.login(email='user3@foo.com', password='pass')
        self.assertFalse(self.o2.is_member(self.u3))
        self.assertFalse(self.o2.has_permission(self.u3, 'can_delete_org'))

        for page in page_list:
            resp = self.client.get(page)
            self.assertEqual(resp.status_code, 302)

        self.o2.register_user(self.u3, role='m1')

        for page in page_list:
            resp = self.client.get(page)
            self.assertEqual(resp.status_code, 302)

        self.client.logout()
