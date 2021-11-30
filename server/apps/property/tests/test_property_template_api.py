import json

from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin

from ..models import GenericPropertyOrgEnum, GenericPropertyOrgTemplate

user_model = get_user_model()


class GenericPropertyOrgTemplateAPITests(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()

    def tearDown(self):
        GenericPropertyOrgTemplate.objects.all().delete()
        GenericPropertyOrgEnum.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testPostPropertyTemplate(self):
        """
        Ensure we can create a new Org object.
        """
        url = reverse('propertytemplate-list')
        data = {
            'name':'Customer',
            'org': self.o2.slug,
            'extra': {
                'random': True
            }
        }

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertTrue(deserialized['extra']['random'])

        # Don't accept duplicate names
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['non_field_errors'], ['The fields org, name must make a unique set.'])

        self.client.logout()

    def testGetPropertyTemplate(self):
        url = reverse('propertytemplate-list')

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        p1 = GenericPropertyOrgTemplate.objects.create(name='F1', org=self.o2, created_by=self.u2, type='enum')
        GenericPropertyOrgEnum.objects.create(value='a', org=self.o2, created_by=self.u2, template=p1)
        GenericPropertyOrgEnum.objects.create(value='b', org=self.o2, created_by=self.u2, template=p1)
        p2 = GenericPropertyOrgTemplate.objects.create(name='F2', org=self.o3, created_by=self.u3)
        detail_url = reverse('propertytemplate-detail', kwargs={'pk': str(p1.id)})
        enum_url = reverse('propertytemplate-enum', kwargs={'pk': str(p1.id)})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        resp = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        resp = self.client.get(url+'?staff=1&org={}'.format(self.o2.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.get(detail_url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], p1.id)
        self.assertEqual(deserialized['name'], str(p1.name))

        resp = self.client.get(enum_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.get(enum_url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

        # Staff has access to all
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], p1.id)

        resp = self.client.get(enum_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.get(enum_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        detail_url = reverse('propertytemplate-detail', kwargs={'pk': str(p2.id)})
        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testGetPropertyTemplateEnums(self):
        url = reverse('propertytemplate-list')

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        p1 = GenericPropertyOrgTemplate.objects.create(name='F1', org=self.o2, created_by=self.u2, type='enum')
        GenericPropertyOrgEnum.objects.create(value='a', org=self.o2, created_by=self.u2, template=p1)
        GenericPropertyOrgEnum.objects.create(value='b', org=self.o2, created_by=self.u2, template=p1)
        GenericPropertyOrgTemplate.objects.create(name='F2', org=self.o3, created_by=self.u3)
        detail_url = reverse('propertytemplate-detail', kwargs={'pk': str(p1.id)})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(len(deserialized['results'][0]['enums']), 2)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        enums = deserialized['enums']
        self.assertEqual(len(enums), 2)
        self.assertTrue('a' in enums)
        self.assertTrue('b' in enums)
        self.assertFalse('c' in enums)

        enum_url = reverse('propertytemplate-enum', kwargs={'pk': str(p1.id)})
        resp = self.client.get(enum_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        for item in deserialized['results']:
            self.assertTrue(item['value'] in enums)

        self.client.logout()

    def testPostPropertyTemplateEnums(self):
        p1 = GenericPropertyOrgTemplate.objects.create(name='F1', org=self.o2, created_by=self.u2, type='enum')
        self.assertEqual(p1.enums.count(), 0)

        enum_url = reverse('propertytemplate-enum', kwargs={'pk': str(p1.id)})

        resp = self.client.get(enum_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {'value': 'a'}
        resp = self.client.post(enum_url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(p1.enums.count(), 1)
        self.assertEqual(p1.enums.first().value, 'a')
        payload = {'value': 'a'}
        resp = self.client.post(enum_url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(p1.enums.count(), 1)
        self.assertEqual(p1.enums.first().value, 'a')
        payload = {'value': 'b'}
        resp = self.client.post(enum_url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(p1.enums.count(), 2)
        self.assertEqual(p1.enums.order_by('value').first().value, 'a')
        self.assertEqual(p1.enums.order_by('value').last().value, 'b')

        self.client.logout()

    def testDeletePropertyTemplateEnums(self):
        p1 = GenericPropertyOrgTemplate.objects.create(name='F1', org=self.o2, created_by=self.u2, type='enum')
        e1 = GenericPropertyOrgEnum.objects.create(value='a', org=self.o2, created_by=self.u2, template=p1)
        GenericPropertyOrgEnum.objects.create(value='b', org=self.o2, created_by=self.u2, template=p1)
        GenericPropertyOrgTemplate.objects.create(name='F2', org=self.o3, created_by=self.u3)
        self.assertEqual(GenericPropertyOrgTemplate.objects.count(), 2)
        self.assertEqual(p1.enums.count(), 2)

        enum_url = reverse('propertytemplate-enum', kwargs={'pk': str(p1.id)})

        payload = {'value': e1.value}
        resp = self.client.delete(enum_url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {}
        resp = self.client.delete(enum_url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        payload = {'value': 'foo'}
        resp = self.client.delete(enum_url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        payload = {'value': e1.value}
        resp = self.client.delete(enum_url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(GenericPropertyOrgTemplate.objects.count(), 2)
        self.assertEqual(p1.enums.count(), 1)
        self.assertEqual(p1.enums.first().value, 'b')

        self.client.logout()
