import json

from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.datablock.models import DataBlock
from apps.physicaldevice.models import Device
from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()


class GenericPropertyOrgTemplateAPITests(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.d1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.d2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)
        self.b1 = DataBlock.objects.create(org=self.p1.org, title='Block1', device=self.d1, block=1, created_by=self.u2)
        self.b2 = DataBlock.objects.create(org=self.p1.org, title='Block2', device=self.d1, block=2, created_by=self.u2)

    def tearDown(self):
        Device.objects.all().delete()
        DataBlock.objects.all().delete()
        GenericProperty.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testPostProperty(self):
        """
        Ensure we can create a new Property object.
        """
        url = reverse('property-list')
        data = {
            'target': self.d1.slug,
            'name': 'P1',
            'str_value': 'Foo'
        }
        self.assertEqual(GenericProperty.objects.count(), 0)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['target'], self.d1.slug)
        self.assertEqual(GenericProperty.objects.count(), 1)

        # Duplicate not allowed
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Ensure we can't create a Property with wrong int_value
        data = {
            'target': self.d1.slug,
            'name': 'P2',
            'int_value': ''
        }
        self.assertEqual(GenericProperty.objects.count(), 1)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(GenericProperty.objects.count(), 1)

        data = {
            'target': self.d1.slug,
            'name': 'P3',
            'int_value': 'wrong'
        }
        self.assertEqual(GenericProperty.objects.count(), 1)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(GenericProperty.objects.count(), 1)

        self.client.logout()

    def testGetProperty(self):
        prop1 = GenericProperty.objects.create_int_property(slug=self.d1.slug,
                                                            created_by=self.u1,
                                                            name='prop1', value=4)
        prop2 = GenericProperty.objects.create_str_property(slug=self.d1.slug,
                                                            created_by=self.u1,
                                                            name='prop2', value='4')
        prop3 = GenericProperty.objects.create_bool_property(slug=self.d2.slug,
                                                             created_by=self.u1,
                                                             name='prop3', value=True)

        url = reverse('property-list') + '?target={}'.format(self.d1.slug)
        detail_url = reverse('property-detail', kwargs={'pk': str(prop1.id)})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

        # Staff has access to all
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], prop1.id)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        url = reverse('property-list') + '?target={}'.format(self.d2.slug)
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testGetPropertyNoTarget(self):
        prop1 = GenericProperty.objects.create_int_property(slug=self.d1.slug,
                                                            created_by=self.u1,
                                                            name='prop1', value=4)
        prop2 = GenericProperty.objects.create_str_property(slug=self.d1.slug,
                                                            created_by=self.u1,
                                                            name='prop2', value='4')
        prop3 = GenericProperty.objects.create_bool_property(slug=self.d2.slug,
                                                             created_by=self.u1,
                                                             name='prop3', value=True)

        url = reverse('property-list')

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['detail'], 'target argument (e.g. target=d--0000-0000-0000-1234) is required')

        # Illegal Target
        resp = self.client.get(url + '?target=foo', format='json')
        self.assertEqual(resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)

        # Also test we can handle target for object that does snot exist
        resp = self.client.get(url + '?target=d--ffff-1111-1111-1111', format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testDeleteProperty(self):
        prop1 = GenericProperty.objects.create_int_property(slug=self.d1.slug,
                                                            created_by=self.u1,
                                                            name='prop1', value=4)
        prop2 = GenericProperty.objects.create_str_property(slug=self.d1.slug,
                                                            created_by=self.u1,
                                                            name='prop2', value='4')
        prop3 = GenericProperty.objects.create_bool_property(slug=self.d1.slug,
                                                             created_by=self.u1,
                                                             name='prop3', value=True)
        self.assertEqual(GenericProperty.objects.count(), 3)

        url = reverse('property-detail', kwargs={'pk': str(prop1.id)})

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(GenericProperty.objects.count(), 2)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        url = reverse('property-detail', kwargs={'pk': str(prop2.id)})
        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(GenericProperty.objects.count(), 1)

        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        url = reverse('property-detail', kwargs={'pk': str(prop3.id)})
        resp = self.client.delete(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testPatchProperty(self):
        prop1 = GenericProperty.objects.create_int_property(slug=self.d1.slug,
                                                            created_by=self.u1,
                                                            name='prop1', value=4)
        prop2 = GenericProperty.objects.create_str_property(slug=self.d1.slug,
                                                            created_by=self.u1,
                                                            name='prop2', value='4')
        prop3 = GenericProperty.objects.create_bool_property(slug=self.d1.slug,
                                                             created_by=self.u1,
                                                             name='prop3', value=True)
        self.assertEqual(GenericProperty.objects.count(), 3)

        url = reverse('property-detail', kwargs={'pk': str(prop1.id)})
        data = {
            'target': self.d1.slug,
            'name': 'prop1',
            'int_value': 5
        }

        resp = self.client.patch(url, data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.patch(url, data=data, format='json')

        # Ensure that the Response body contains the new object
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['value'], 5)

        # Ensure that when we GET the new object, the value has changed
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['value'], 5)

        self.assertEqual(GenericProperty.objects.count(), 3)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        data['int_value'] = 6
        resp = self.client.patch(url, data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['value'], 6)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.patch(url, data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()
