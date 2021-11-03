import json
import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.test import TestCase

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.devicetemplate.models import DeviceTemplate
from apps.utils.test_util import TestMixin
from apps.devicescript.models import DeviceScript

from apps.physicaldevice.worker.device_status_check import DeviceStatusCheckAction
from ..models import *

user_model = get_user_model()


class DeviceFirmwareVersionAPITestCase(TestMixin, TestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        DeviceStatus.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()
        self.projectTestTearDown()

    def testStatusModel(self):
        d1 = Device.objects.create_device(project=self.p2, label='d1', template=self.dt1, created_by=self.u1)
        st = DeviceStatus.get_or_create(d1)
        self.assertIsNotNone(st)
        self.assertEqual(st.last_known_id, 1)
        self.assertEqual(st.last_known_state, 'UNK')

    def testStatusAlert(self):
        d1 = Device.objects.create_device(project=self.p2, label='d1', template=self.dt1, created_by=self.u1)
        st = DeviceStatus.get_or_create(d1)
        self.assertEqual(st.alert, 'DSBL')
        st.health_check_enabled = True
        self.assertEqual(st.alert, 'UNK')
        st.last_report_ts = timezone.now() - datetime.timedelta(seconds=7199)
        self.assertEqual(st.alert, 'OK')
        st.last_report_ts = timezone.now() - datetime.timedelta(seconds=7201)
        self.assertEqual(st.alert, 'FAIL')

    def testViewAccess(self):
        d1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        st = DeviceStatus.get_or_create(d1)
        self.assertFalse(st.health_check_enabled)
        status_url = reverse('org:project:device:health-status', kwargs={
            'org_slug':self.p1.org.slug, 'project_id': self.p1.id, 'pk': d1.id
        })
        settings_url = reverse('org:project:device:health-settings', kwargs={
            'org_slug':self.p1.org.slug, 'project_id': self.p1.id, 'pk': d1.id
        })

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(status_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get(settings_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = {'recipients' : ['org:all'],
                   'extras' : '',
                   'health_check_enabled': True,
                   'health_check_period' : 3800}
        response = self.client.post(settings_url, payload)
        self.assertRedirects(response, expected_url=status_url, status_code=302, target_status_code=200)
        st = DeviceStatus.get_or_create(d1)
        self.assertTrue(st.health_check_enabled)
        self.assertEqual(st.health_check_period, 3800)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(status_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get(settings_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = {'recipients' : ['org:all'],
                   'extras' : '',
                   'health_check_enabled': False,
                   'health_check_period' : 3600}
        response = self.client.post(settings_url, payload)
        self.assertRedirects(response, expected_url=status_url, status_code=302, target_status_code=200)
        st = DeviceStatus.get_or_create(d1)
        self.assertFalse(st.health_check_enabled)
        self.assertEqual(st.health_check_period, 3600)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(status_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.get(settings_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.post(settings_url, payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    @mock.patch('apps.emailutil.tasks.Email.send_email')
    def testWorker(self, mock_email):
        d1 = Device.objects.create_device(project=self.p2, label='d1', template=self.dt1, created_by=self.u1)
        d2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u1)
        st2 = DeviceStatus.get_or_create(d2)

        action = DeviceStatusCheckAction()
        action._process_checks()

        mock_email.return_value = None
        self.assertFalse(mock_email.called)
        st = DeviceStatus.get_or_create(d1)
        self.assertEqual(st.last_known_state, 'UNK')
        st.health_check_enabled = True
        st.last_report_ts = timezone.now() - datetime.timedelta(seconds=7199)
        st.save()
        action._process_checks()
        st = DeviceStatus.get_or_create(d1)
        self.assertEqual(st.last_known_state, 'OK')
        self.assertEqual(st2.last_known_state, 'UNK')
        self.assertTrue(mock_email.called)

        mock_email.return_value = None
        mock_email.called = False
        self.assertFalse(mock_email.called)
        st = DeviceStatus.get_or_create(d1)
        st.health_check_enabled = True
        st.last_report_ts = timezone.now() - datetime.timedelta(seconds=7201)
        st.save()
        action._process_checks()
        st = DeviceStatus.get_or_create(d1)
        self.assertEqual(st.last_known_state, 'FAIL')
        self.assertTrue(mock_email.called)
