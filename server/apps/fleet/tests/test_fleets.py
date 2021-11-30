import datetime
import json

import dateutil.parser

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.utils import dateparse, timezone

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.physicaldevice.models import Device
from apps.utils.gid.convert import *
from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()


class FleetTests(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.d1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.d2 = Device.objects.create_device(project=self.p1, label='d2', template=self.dt1, created_by=self.u3)

    def tearDown(self):
        FleetMembership.objects.all().delete()
        Fleet.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testFleetMembership(self):
        fleet1 = Fleet.objects.create(name='F1', org=self.o2, created_by=self.u2)
        self.assertEqual(FleetMembership.objects.count(), 0)
        fleet1.register_device(self.d1)
        self.assertEqual(FleetMembership.objects.count(), 1)
        self.assertEqual(fleet1.members.first().id, self.d1.id)
        self.assertEqual(self.d1.fleet_set.first().id, fleet1.id)
        self.assertTrue(fleet1.is_member(self.d1))
        self.assertFalse(fleet1.is_member(self.d2))

        fleet1.register_device(self.d2)
        self.assertTrue(fleet1.is_member(self.d2))
        self.assertEqual(FleetMembership.objects.count(), 2)
        self.assertEqual(fleet1.members.count(), 2)

    def testIllegalFleetMembership(self):
        f = Fleet.objects.create(name='F1', org=self.o3, created_by=self.u2)
        with self.assertRaises(ValidationError):
            f.register_device(self.d1)

    def testObjectAccess(self):
        f1 = Fleet.objects.create(name='F1', org=self.o2, created_by=self.u2)
        f2 = Fleet.objects.create(name='F2', org=self.o3, created_by=self.u3)
        self.assertTrue(f1.has_access(self.u1))
        self.assertTrue(f1.has_access(self.u2))
        self.assertFalse(f1.has_access(self.u3))
        self.assertTrue(f2.has_access(self.u1))
        self.assertFalse(f2.has_access(self.u2))
        self.assertTrue(f2.has_access(self.u3))

    def testBasicGetViews(self):
        fleet1 = Fleet.objects.create(name='F1', org=self.o2, created_by=self.u2)
        fleet2 = Fleet.objects.create(name='F2', org=self.o2, created_by=self.u2)
        fleet1.register_device(self.d1)
        self.assertEqual(FleetMembership.objects.count(), 1)
        member1 = FleetMembership.objects.filter(fleet=fleet1).first()

        # GET
        url_list = [
            reverse('org:fleet:list',
                    kwargs={'org_slug': self.o2.slug}),
            reverse('org:fleet:detail',
                    kwargs={'org_slug': self.o2.slug, 'slug': fleet1.slug}),
            reverse('org:fleet:detail',
                    kwargs={'org_slug': self.o2.slug, 'slug': fleet2.slug}),
            reverse('org:fleet:add',
                    kwargs={'org_slug': self.o2.slug}),
            reverse('org:fleet:edit',
                    kwargs={'org_slug': self.o2.slug, 'slug': fleet1.slug}),
            reverse('org:fleet:member-add',
                    kwargs={'org_slug': self.o2.slug, 'slug': fleet1.slug}),
            reverse('org:fleet:member-edit',
                    kwargs={'org_slug': self.o2.slug, 'slug': fleet1.slug, 'pk': member1.id}),
            reverse('org:fleet:member-delete',
                    kwargs={'org_slug': self.o2.slug, 'slug': fleet1.slug, 'pk': member1.id}),
        ]
        for url in url_list:
            response = self.client.get(url)
            self.assertRedirects(response, '/account/login/?next={0}'.format(url))

            ok = self.client.login(email=self.u1.email, password='pass')
            self.assertTrue(ok)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK, msg=url)

            self.client.logout()

            ok = self.client.login(email=self.u2.email, password='pass')
            self.assertTrue(ok)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_302_FOUND, msg=url)

            self.client.logout()

            ok = self.client.login(email=self.u3.email, password='pass')
            self.assertTrue(ok)

            self.o2.de_register_user(self.u3, delete_obj=True)
            self.assertFalse(self.o2.is_member(self.u3))
            self.assertFalse(self.o2.has_permission(self.u3, 'can_manage_ota'))
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_302_FOUND, msg=url)

            membership = self.o2.register_user(self.u3, role='m1')
            membership.permissions['can_manage_ota'] = True
            membership.save()

            self.assertTrue(self.o2.has_permission(self.u3, 'can_manage_ota'))
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK, msg=url)

            self.client.logout()

    def testCreateForms(self):
        url1 = reverse('org:fleet:add', kwargs={'org_slug': self.o2.slug})

        response = self.client.get(url1)
        self.assertRedirects(response, expected_url='/account/login/?next={}'.format(url1))

        self.assertEqual(Fleet.objects.count(), 0)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertEqual(ok, True)

        response = self.client.get(url1, follow=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertTrue(self.o2.has_access(self.u1))
        payload = {
            'name': 'Fleet 1'
        }
        response = self.client.post(url1, payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(Fleet.objects.count(), 1)
        self.assertEqual(FleetMembership.objects.count(), 0)

        fleet1 = Fleet.objects.first()
        url_add_member = reverse('org:fleet:member-add', kwargs={'org_slug': self.o2.slug, 'slug': fleet1.slug})

        payload = {
            'device': self.d1.id,
            'always_on': True
        }
        response = self.client.post(url_add_member, payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(FleetMembership.objects.count(), 1)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertEqual(ok, True)

        self.assertFalse(self.o2.has_write_access(self.u3))
        payload = {
            'name': 'Fleet 2'
        }
        response = self.client.post(url1, payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(Fleet.objects.count(), 1)

        payload = {
            'device': self.d2.id,
            'always_on': True
        }
        response = self.client.post(url_add_member, payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(FleetMembership.objects.count(), 1)

        self.client.logout()

    def testUpdateForms(self):
        fleet1 = Fleet.objects.create(name='F1', org=self.o2, created_by=self.u2)
        fleet1.register_device(self.d1)
        fm1 = FleetMembership.objects.first()
        url_fleet = reverse('org:fleet:edit', kwargs={'org_slug': self.o2.slug, 'slug': fleet1.slug})
        url_member = reverse('org:fleet:member-edit',
                             kwargs={'org_slug': self.o2.slug, 'slug': fleet1.slug, 'pk': fm1.id})
        url_member_delete = reverse('org:fleet:member-delete',
                                    kwargs={'org_slug': self.o2.slug, 'slug': fleet1.slug, 'pk': fm1.id})

        payload_fleet = {
            'name': 'F1B',
            'is_network': True
        }
        payload_device = {
            'always_on': True
        }

        response = self.client.post(url_fleet, payload_fleet)
        self.assertRedirects(response, expected_url='/account/login/?next={}'.format(url_fleet))
        response = self.client.post(url_member)
        self.assertRedirects(response, expected_url='/account/login/?next={}'.format(url_member))

        self.assertEqual(Fleet.objects.count(), 1)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertEqual(ok, True)

        response = self.client.get(url_fleet, follow=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertTrue(self.o2.has_access(self.u2))
        response = self.client.post(url_fleet, payload_fleet)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(Fleet.objects.count(), 1)

        response = self.client.post(url_member, payload_device)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertEqual(ok, True)

        self.assertFalse(self.o2.has_access(self.u3))
        response = self.client.post(url_fleet, payload_fleet)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(Fleet.objects.count(), 1)

        response = self.client.post(url_member, payload_device)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(FleetMembership.objects.count(), 1)

        # Try again, but as non-admin member
        membership = self.o2.register_user(user=self.u3, role='m1')
        membership.permissions['can_manage_ota'] = True
        membership.save()

        payload_fleet['name'] = 'foo'
        response = self.client.post(url_fleet, payload_fleet)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(Fleet.objects.count(), 1)
        fleet1 = Fleet.objects.first()
        self.assertEqual(fleet1.name, 'foo')

        response = self.client.post(url_member, payload_device)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(FleetMembership.objects.count(), 1)

        response = self.client.post(url_member_delete, {})
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(FleetMembership.objects.count(), 0)

        self.client.logout()
