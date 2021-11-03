import datetime
import time
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.contrib.messages import get_messages

from rest_framework import status

from apps.utils.test_util import TestMixin
from apps.physicaldevice.models import Device
from apps.devicetemplate.models import DeviceTemplate
from apps.projecttemplate.models import ProjectTemplate
from apps.project.models import Project
from apps.org.models import Org

user_model = get_user_model()

class DeviceSupportTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

        self.staff = user_model.objects.create_user(username='staff', email='staff@acme.com', password='pass')
        self.staff.is_active = True
        self.staff.is_admin = False
        self.staff.is_staff = True
        self.staff.save()

        self.org_admin = user_model.objects.create_user(username='org_admin', email='org_admin@acme.com', password='pass')
        self.org_admin.is_active = True
        self.org_admin.is_admin = False
        self.org_admin.is_staff = False
        self.org_admin.save()
        self.o1.register_user(self.org_admin, role='a0')

        self.user = user_model.objects.create_user(username='user', email='user@acme.com', password='pass')
        self.user.is_active = True
        self.user.is_admin = False
        self.user.is_staff = False
        self.user.save()

    def tearDown(self):
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testAccessControls(self):

        d1 = Device.objects.create_device(project=self.p2, label='d1', template=self.dt1, created_by=self.u1)

        url_list = {
            reverse('vendor:home', kwargs={'slug': self.o1.slug}): 'org-member-only',
            reverse('vendor:project-list', kwargs={'slug': self.o1.slug}): 'org-member-only',
            reverse('vendor:map', kwargs={'slug': self.o1.slug}): 'org-member-only',
            reverse('vendor:dt-list', kwargs={'slug': self.o1.slug}): 'open',
            reverse('vendor:sg-matrix', kwargs={'slug': self.o1.slug}): 'org-member-only',
            reverse('vendor:product-matrix', kwargs={'slug': self.o1.slug}): 'org-member-only',
            reverse('vendor:device-detail', kwargs={'slug': self.o1.slug, 'pk': d1.id}): 'org-member-only',
        }
        for url, perm_type in url_list.items():
            response = self.client.get(url)
            self.assertRedirects(response, '/account/login/?next={0}'.format(url))

            ok = self.client.login(email='staff@acme.com', password='pass')
            self.assertTrue(ok)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.client.logout()

            ok = self.client.login(email='org_admin@acme.com', password='pass')
            self.assertTrue(ok)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.client.logout()

            ok = self.client.login(email='user@acme.com', password='pass')
            self.assertTrue(ok)

            response = self.client.get(url)
            if perm_type == 'org-member-only':
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN,
                                msg="User %s, accessing %s, received %s"
                                % ('user@acme.com', url, response.status_code))
            else:
                self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.client.logout()
