import datetime
import json
import dateutil.parser

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from rest_framework import status

from apps.physicaldevice.models import Device
from apps.streamfilter.models import *
from apps.utils.gid.convert import *
from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()


class DeviceLocationTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)

    def tearDown(self):
        DeviceLocation.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testLocation(self):
        location = DeviceLocation.objects.create(
            timestamp=timezone.now(),
            target_slug=self.pd1.slug,
            user=self.u2
        )
        self.assertIsNotNone(location)
        self.assertEqual(location.target.id, self.pd1.id)

    def testMemberPermissions(self):
        """
        Test that people with no permissions cannot access
        """

        map_url = reverse('devicelocation:map', kwargs={'slug': self.pd1.slug})

        self.client.login(email='user3@foo.com', password='pass')
        membership = self.p1.org.register_user(self.u3, role='m1')
        membership.permissions['can_read_device_locations'] = False
        membership.save()

        resp = self.client.get(map_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        membership.permissions['can_read_device_locations'] = True
        membership.permissions['can_access_classic'] = False
        membership.save()

        resp = self.client.get(map_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

