import json
import datetime
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.org.models import Org, OrgMembership
from apps.component.models import Component
from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()

class DeviceTemplateTestCase(TestMixin, TestCase):
    """
    Fixure includes:
    """
    #fixtures = ['testdb_main.json']

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()

    def tearDown(self):
        Component.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasicDeviceObject(self):
        c1 = Component.objects.create(external_sku='IOTile 1', type='1', created_by=self.u2)
        c2 = Component.objects.create(external_sku='IOTile 2', type='1', created_by=self.u2)
        c3 = Component.objects.create(external_sku='Carrier', type='2', created_by=self.u2)
        d1 = DeviceTemplate.objects.create(external_sku='Device 1',
                                           major_version=1, released_on=timezone.now(),
                                           created_by=self.u2, org=self.o2)
        d1.components.add(c1)
        d1.components.add(c2)
        d1.components.add(c3)
        self.assertEqual(str(d1), 'Device 1 (v1.0.0)')
        self.assertEqual(d1.slug, 'device-1-v1-0-0')
        self.assertEqual(d1.components.count(), 3)
        self.assertEqual(d1.os_tag_and_version, '0 v0.0')
        self.assertEqual(d1.hw_tag_and_version, '0 v0')

    def testDeviceTagsObject(self):
        d1 = DeviceTemplate.objects.create(
            external_sku='Device 1',
            major_version=1,
            released_on=timezone.now(),
            os_tag=2050,
            os_major_version=1,
            os_minor_version=2,
            hw_tag=1024,
            hw_major_version=1,
            created_by=self.u2,
            org=self.o2
        )
        self.assertEqual(d1.os_tag_and_version, '2050 v1.2')
        self.assertEqual(d1.hw_tag_and_version, '1024 v1')
        self.assertEqual(d1.os_version, 'v1.2')
        self.assertEqual(d1.hw_version, 'v1')

    def testManagerCreate(self):
        device = DeviceTemplate.objects.create_template(external_sku='Device 1',
                                                        released_on=timezone.now(),
                                                        created_by=self.u2, org=self.o2)
        self.assertIsNotNone(device)
        self.assertEqual(device.external_sku, 'Device 1')
        self.assertEqual(device.name, 'Device 1')
        self.assertEqual(DeviceTemplate.objects.count(), 1)

        device = DeviceTemplate.objects.create_template(external_sku='Device 2',
                                                        released_on=timezone.now(),
                                                        created_by=self.u2, org=self.o2)
        self.assertIsNotNone(device)
        self.assertEqual(DeviceTemplate.objects.count(), 2)

    def testObjectAccess(self):
        d1 = DeviceTemplate.objects.create_template(external_sku='Device 1',
                                                    released_on=timezone.now(),
                                                    created_by=self.u2, org=self.o2)
        d2 = DeviceTemplate.objects.create_template(external_sku='Device 2',
                                                    released_on=timezone.now(),
                                                    active=False,
                                                    created_by=self.u3, org=self.o3)
        self.assertTrue(d1.has_access(self.u1))
        self.assertTrue(d1.has_access(self.u2))
        self.assertTrue(d1.has_access(self.u3))
        self.assertTrue(d2.has_access(self.u1))
        self.assertFalse(d2.has_access(self.u2))
        self.assertTrue(d2.has_access(self.u3))

    def testBasicDeviceGet(self):
        d1 = DeviceTemplate.objects.create_template(external_sku='Device 1',
                                                    released_on=timezone.now(),
                                                    created_by=self.u2, org=self.o2)
        d2 = DeviceTemplate.objects.create_template(external_sku='Device 2',
                                                    released_on=timezone.now(),
                                                    created_by=self.u2, org=self.o2)
        d3 = DeviceTemplate.objects.create_template(external_sku='Device 3',
                                                    released_on=timezone.now(),
                                                    active=False,
                                                    created_by=self.u3, org=self.o3)

        url_detail1 = reverse('template:detail', kwargs={'slug': d1.slug})
        url_detail3 = reverse('template:detail', kwargs={'slug': d3.slug})

        resp = self.client.get(url_detail1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)

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

        d3.active = True
        d3.save()
        ok = self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(url_detail3, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testAddComponentToDevicePost(self):
        d1 = DeviceTemplate.objects.create_template(external_sku='Device 1',
                                                    released_on=timezone.now(),
                                                    created_by=self.u2, org=self.o2)
        c1 = Component.objects.create(external_sku='Comp 1', type='IOT', created_by=self.u1)
        c2 = Component.objects.create(external_sku='Comp 2', type='IOT', created_by=self.u1)
        c3 = Component.objects.create(external_sku='Comp 3', type='IOT', created_by=self.u1)

        url = reverse('template:component-add', kwargs={'slug': d1.slug})
        payload = {'components': c1.id, 'slot_number': 1}

        self.assertEqual(d1.slots.count(), 0)

        resp = self.client.get(url, format='json')
        self.assertRedirects(resp, expected_url='/account/login/?next='+url, status_code=302, target_status_code=200)

        resp = self.client.post(url, payload, format='json')
        self.assertRedirects(resp, expected_url='/account/login/?next='+url, status_code=302, target_status_code=200)

        ok = self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.post(url, payload, format='json')
        successful_url = reverse('template:detail', kwargs={'slug': d1.slug})
        self.assertRedirects(resp, expected_url=successful_url, status_code=302, target_status_code=200)

        self.assertEqual(d1.slots.count(), 1)

        successful_url = reverse('template:detail', kwargs={'slug': d1.slug})
        self.assertRedirects(resp, expected_url=successful_url, status_code=302, target_status_code=200)

        self.assertEqual(d1.slots.count(), 1)

        slot = DeviceSlot.objects.first()
        self.assertEqual(slot.template, d1)
        self.assertEqual(slot.component, c1)

        self.client.logout()


class DeviceTemplateAPITestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()

    def tearDown(self):
        Component.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testPost(self):
        url = reverse('devicetemplate-list')

        payload = {
            'external_sku': 'foo',
            'org': str(self.o1.slug),
            'major_version': 2, 'patch_version': 1,
            'os_tag': 2050,
            'os_major_version': 1,
            'hw_tag': 1024,
            'hw_major_version': 1,
            'released_on': '2016-09-23'
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['version'], 'v2.0.1')
        self.assertEqual(deserialized['os_tag'], 2050)
        self.assertEqual(deserialized['os_version'], 'v1.0')
        self.assertEqual(deserialized['hw_tag'], 1024)
        self.assertEqual(deserialized['hw_version'], 'v1')

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testSlotsAccess(self):
        d1 = DeviceTemplate.objects.create_template(external_sku='Device 1',
                                                    released_on=timezone.now(),
                                                    created_by=self.u2, org=self.o2)
        c1 = Component.objects.create(external_sku='Comp 1', type='IOT', created_by=self.u1, hw_tag='hwtag 1')
        slot = DeviceSlot.objects.create(template=d1, component=c1, number=0)
        url_slot = reverse('devicetemplate-slot', kwargs={'slug': str(d1.slug)})
        url_slot_detail = url_slot + '{}/'.format(slot.id)
        payload = {
            "component": c1.slug,
            "number": 0
        }
        # Before logging in
        response = self.client.get(url_slot, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.get(url_slot_detail, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        response = self.client.post(url_slot, data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.put(url_slot, payload)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.patch(url_slot, payload)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.delete(url_slot, payload)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url_slot, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get(url_slot_detail, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        response = self.client.put(url_slot, payload)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        response = self.client.patch(url_slot, payload)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        response = self.client.delete(url_slot, payload)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        self.client.logout()

    def testSlots(self):
        # Create a DT & Component
        d1 = DeviceTemplate.objects.create_template(external_sku='Device 1',
                                                    released_on=timezone.now(),
                                                    created_by=self.u2, org=self.o2)
        c1 = Component.objects.create(external_sku='Comp 1', type='IOT', created_by=self.u1, hw_tag='hwtag 1')
        c2 = Component.objects.create(external_sku='Comp 2', type='IOT', created_by=self.u1, hw_tag='hwtag 2')
        c3 = Component.objects.create(external_sku='Comp 3', type='IOT', created_by=self.u1, hw_tag='hwtag 3')

        url_slot = reverse('devicetemplate-slot', kwargs={'slug': str(d1.slug)})
        slots = {}

        payload = {
            "number": 0,
            "component": c1.slug
        }

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        # Add a slot
        response = self.client.post(url_slot, data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['number'], payload['number'])
        self.assertEqual(deserialized['component'], c1.slug)
        slots[0] = deserialized

        # Get slots
        response = self.client.get(url_slot, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        result = deserialized['results'][0]
        self.assertEqual(result['number'], payload['number'])
        self.assertEqual(result['component'], c1.slug)
        self.assertEqual(result['hw_tag'], c1.hw_tag)

        # Add another slot
        payload = {
            "number": 1,
            "component": c2.slug
        }
        response = self.client.post(url_slot, data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['number'], payload['number'])
        self.assertEqual(deserialized['component'], c2.slug)
        slots[1] = deserialized

        # Get slots
        response = self.client.get(url_slot, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)
        for result in deserialized['results']:
            expected_slot = slots[result['number']]
            for key in ['component', 'number']:
                self.assertEqual(result[key], expected_slot[key])

        # Update a slot
        payload = {
            "number": 0,
            "component": c2.slug
        }
        response = self.client.post(url_slot, data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['number'], payload['number'])
        self.assertEqual(deserialized['component'], c2.slug)
        slots[0] = deserialized

        # Get slots
        response = self.client.get(url_slot, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)
        for result in deserialized['results']:
            expected_slot = slots[result['number']]
            for key in ['component', 'number']:
                self.assertEqual(result[key], expected_slot[key])

        self.client.logout()
