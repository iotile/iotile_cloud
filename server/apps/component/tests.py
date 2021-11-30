import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.devicetemplate.models import DeviceTemplate
from apps.org.models import Org, OrgMembership
from apps.project.models import Project
from apps.utils.test_util import TestMixin

from .models import *

user_model = get_user_model()


class ComponentTestCase(TestMixin, TestCase):
    """
    Fixure includes:
    """
    #fixtures = ['testdb_main.json']

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        Component.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasicComponentObject(self):
        c1 = Component.objects.create(external_sku='Comp1', type='IOT', created_by=self.u2)
        self.assertEqual(str(c1), 'Comp1 (v0.0.0)')
        self.assertEqual(c1.slug, 'comp1-0-0-0')


class DeviceAPITestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        Component.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testPostComponent(self):
        """
        Ensure we can create a new component object.
        """
        url = reverse('component-list')
        board = {
            'external_sku':'CAR 1',
            'type': 'BTC',
            'minor_version': 2
        }

        #Only logged in users should be allowed to create. Test that
        response = self.client.post(url, board, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, board, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Component.objects.count(), 2)

        self.client.logout()

        # Only Staff is allowed to Write. Test that
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        data = {
            'external_sku':'Tile 2',
            'type': 'IOT',
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Component.objects.count(), 2)
        self.client.logout()

    def testGetComponent(self):
        """
        Ensure we can call GET on the org API.
        """
        url = reverse('component-list')

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        c1 = Component.objects.create(external_sku='IOTile 1', type='IOT',  created_by=self.u2)
        c2 = Component.objects.create(external_sku='IOTile 2', type='IOT', created_by=self.u2)
        c3 = Component.objects.create(external_sku='Carrier', type='CAR', created_by=self.u2)

        detail_url1 = reverse('component-detail', kwargs={'slug': str(c1.slug)})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)

        resp = self.client.get(detail_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], str(c1.id))
        self.assertEqual(deserialized['external_sku'], str(c1.name))
        self.assertEqual(deserialized['type'], str(c1.type))

        self.client.logout()
