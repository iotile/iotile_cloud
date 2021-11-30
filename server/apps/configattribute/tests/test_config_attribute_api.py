import json

from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.datablock.models import DataBlock
from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.streamnote.models import StreamNote
from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()


class ConfigAttributeAPITests(TestMixin, APITestCase):

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
        ConfigAttribute.objects.all().delete()
        ConfigAttributeName.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testPostConfigAttributeName(self):
        """
        Only Staff can create new configuration attribute names
        """
        url = reverse('configattributename-list')
        data = {
            'name': ':foo'
        }
        self.assertEqual(ConfigAttributeName.objects.count(), 0)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ConfigAttributeName.objects.count(), 1)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['name'], ':foo')

        # Duplicate not allowed
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        data = {
            'name': 'bad_name'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        data = {
            'name': ':bar',
            'description': 'This is a description',
            'tags': ['tag1', 'tag2']
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ConfigAttributeName.objects.count(), 2)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['name'], data['name'])
        self.assertEqual(deserialized['description'], data['description'])
        self.assertEqual(deserialized['tags'][0], data['tags'][0])
        self.assertEqual(deserialized['tags'][1], data['tags'][1])

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testGetConfigAttributeName(self):
        """
        Everybody can get config attr names
        """
        ConfigAttributeName.objects.create(name=':foo', tags=['tag1'], created_by=self.u1)
        ConfigAttributeName.objects.create(name=':bar', created_by=self.u1)
        ConfigAttributeName.objects.create(name=':foo:bar', tags=['tag1', 'tag2'], created_by=self.u1)
        self.assertEqual(ConfigAttributeName.objects.count(), 3)
        url = reverse('configattributename-list')

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url + '?name_q=foo', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        response = self.client.get(url + '?tag=tag1', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        response = self.client.get(url + '?tag=tag2', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

    def testGetConfigAttribute(self):
        """
        Everybody can get config attributes
        """
        foo_attr1 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.o2,
            name=':foo',
            data={'a': 'b'},
            updated_by=self.u1
        )
        foo_attr2 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.o2,
            name=':bar',
            data={'a': 'b'},
            updated_by=self.u1
        )
        foo_attr3 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.o3,
            name=':bar',
            data={'a': 'c'},
            updated_by=self.u1
        )
        foo_attr4 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.u3,
            name=':user',
            data={'a': 'c'},
            updated_by=self.u1
        )

        self.assertEqual(ConfigAttribute.objects.count(), 4)
        url = reverse('configattribute-list')

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(url + '?target={}'.format(self.o2.obj_target_slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url + '?target={}'.format(self.o2.obj_target_slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        response = self.client.get(url + '?target={}'.format(self.o3.obj_target_slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        filter_url = url + '?target={}&name_q=foo'.format(self.o2.obj_target_slug)
        response = self.client.get(filter_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['id'], foo_attr1.id)

        filter_url = url + '?target={}&name_q=bar'.format(self.o2.obj_target_slug)
        response = self.client.get(filter_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['id'], foo_attr2.id)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        self.assertTrue(self.o3.has_access(self.u3))
        response = self.client.get(url + '?target={}'.format(self.o3.obj_target_slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.get(url + '?target={}'.format(self.u3.obj_target_slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

    def testSearchConfigAttribute(self):
        """
        test search path
        """
        project = Project.objects.create(name='Project 2', org=self.o2, created_by=self.u2)
        foo_name = ConfigAttributeName.objects.create(name=':foo', created_by=self.u1)
        bar_name = ConfigAttributeName.objects.create(name=':bar', created_by=self.u1)
        foo_attr1 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.o2,
            name=foo_name,
            data={'a': 'b'},
            updated_by=self.u1
        )
        foo_attr2 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.u1,
            name=foo_name,
            data={'a': 'b'},
            updated_by=self.u1
        )
        bar_attr = ConfigAttribute.objects.get_or_create_attribute(
            target=self.u2,
            name=bar_name,
            data={'c': 'd'},
            updated_by=self.u2
        )

        self.assertEqual(ConfigAttribute.objects.count(), 3)
        url = reverse('configattribute-search')

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        self.assertTrue(project.org.id, self.o2.id)
        search_url = url + '?target={}&name=:foo'.format(project.obj_target_slug)
        response = self.client.get(search_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['id'], foo_attr1.id)

        search_url = url + '?target={}&name=:bar'.format(project.obj_target_slug)
        response = self.client.get(search_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['id'], bar_attr.id)

        search_url = url + '?target={}&name=:foobar'.format(project.obj_target_slug)
        response = self.client.get(search_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

        self.assertEqual(ConfigAttribute.objects.count(), 3)
        url = reverse('configattribute-search')

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        self.assertTrue(project.org.id, self.o2.id)
        search_url = url + '?target={}&name=:foo'.format(project.obj_target_slug)
        response = self.client.get(search_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testPostConfigAttribute(self):
        """
        Test that users can create configuration attributes
        """
        project = Project.objects.create(name='Project 2', org=self.o2, created_by=self.u2)
        url = reverse('configattribute-list')
        data = {
            'name': ':foo',
            'target': project.obj_target_slug,
            'data': {
                'a': 'b'
            }
        }
        self.assertEqual(ConfigAttribute.objects.count(), 0)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        # Configuration Attirbute Name does not exist
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        ConfigAttributeName.objects.create(name=':foo', tags=['tag1'], created_by=self.u1)
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ConfigAttribute.objects.count(), 1)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['name'], ':foo')
        self.assertEqual(deserialized['data']['a'], 'b')

        # Duplicate will be equivalent to PATCH
        data['data']['a'] = 'c'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ConfigAttribute.objects.count(), 1)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['name'], ':foo')
        self.assertEqual(deserialized['data']['a'], 'c')

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        ConfigAttributeName.objects.create(name=':bar', tags=['tag1'], created_by=self.u1)
        data = {
            'name': ':bar',
            'target': project.obj_target_slug,
            'data': {
                'a': 'b'
            }
        }

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testPostBadConfigAttribute(self):
        """
        Test that users gets proper errors if illegal or bad payloads
        """
        project = Project.objects.create(name='Project 2', org=self.o2, created_by=self.u2)
        url = reverse('configattribute-list')
        ConfigAttributeName.objects.create(name=':foo', tags=['tag1'], created_by=self.u1)
        data = {
            'name': ':foo',
            'target': self.d1.obj_target_slug.upper(), # see if we can hanlde upper case
            'data': {
                'a': 'b'
            }
        }
        self.assertEqual(ConfigAttribute.objects.count(), 0)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        data = {
            'name': ':foo',
            'target': self.d2.formatted_gid,
            'data': {
                'a': 'b'
            }
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        d1000 = Device.objects.create_device(id=0x00ff, project=self.d2.project, label='d1', template=self.dt1, created_by=self.u2)
        data = {
            'name': ':foo',
            'target': 'd--0000-0000-0000-00FF',
            'data': {
                'a': 'b'
            }
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.client.logout()

    def testPatchConfigAttribute(self):
        """
        Test that users can't update configuration attributes using PATCH
        """

        project = Project.objects.create(name='Project 2', org=self.o2, created_by=self.u2)
        data = {
            'a': 'b'
        }
        name = ConfigAttributeName.objects.create(name=':foo', tags=['tag1'], created_by=self.u1)
        ca = ConfigAttribute.objects.create(name=name, target=project.obj_target_slug, data=data, updated_by=self.u1)
        self.assertEqual(ConfigAttribute.objects.count(), 1)
        self.assertEqual(ca.data, {'a': 'b'})

        url = reverse('configattribute-detail', kwargs={'pk': ca.id})

        payload = {
            'data': {
                'c': 'd'
            }
        }

        response = self.client.patch(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.patch(url, payload, format='json')
        deserialized = json.loads(response.content.decode())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('error' in deserialized)
        self.assertEqual(deserialized['error'], 'PUT and PATCH methods are not supported; use POST with the right target')
        ca = ConfigAttribute.objects.get(pk=ca.id)
        self.assertEqual(ConfigAttribute.objects.count(), 1)
        self.assertEqual(ca.data, {'a': 'b'})

        self.client.logout()

    def testPostConfigAttributeWithLog(self):
        """
        Test that users can create configuration attributes and make a log
        """
        Project.objects.create(name='Project 2', org=self.o2, created_by=self.u2)
        url = reverse('configattribute-list')
        data = {
            'name': ':foo',
            'target': self.d1.obj_target_slug,
            'log_as_note': True,
            'data': {
                'a': 'b',
                'c': 5
            }
        }
        self.assertEqual(ConfigAttribute.objects.count(), 0)
        self.assertEqual(StreamNote.objects.count(), 0)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        ConfigAttributeName.objects.create(name=':foo', tags=['tag1'], created_by=self.u1)
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ConfigAttribute.objects.count(), 1)
        self.assertEqual(StreamNote.objects.count(), 1)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ConfigAttribute.objects.count(), 1)
        self.assertEqual(StreamNote.objects.count(), 2)

        for item in StreamNote.objects.all():
            self.assertEqual(item.target_slug, self.d1.obj_target_slug)

        self.client.logout()

    def testPostConfigAttributeBadPayload(self):
        """
        Test that users can create configuration attributes
        """
        project = Project.objects.create(name='Project 2', org=self.o2, created_by=self.u2)
        foo_name = ConfigAttributeName.objects.create(name=':foo', created_by=self.u1)
        foo_attr1 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.o2,
            name=foo_name,
            data={'a': 'b'},
            updated_by=self.u1
        )
        url = reverse('configattribute-list')
        url_detail = reverse('configattribute-detail', kwargs={'pk': foo_attr1.id})
        data = {
            'name': ':foo',
            'target': project.obj_target_slug,
            'a': 'b'
        }
        self.assertEqual(ConfigAttribute.objects.count(), 1)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        # Configuration Attirbute Name does not exist
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.content, b'["Required fields: data, target, name"]')

        self.client.logout()

    def testDeleteConfigAttribute(self):
        """
        Test that users can delete configuration attributes
        """
        p = Project.objects.create(name='Project 2', org=self.o2, created_by=self.u2)
        foo_name = ConfigAttributeName.objects.create(name=':foo', created_by=self.u1)
        bar_name = ConfigAttributeName.objects.create(name=':bar', created_by=self.u1)
        foobar_name = ConfigAttributeName.objects.create(name=':foo:bar', created_by=self.u1)
        attr1 = ConfigAttribute.objects.get_or_create_attribute(
            target=p,
            name=foo_name,
            data={'a': 'b'},
            updated_by=self.u1
        )
        attr2 = ConfigAttribute.objects.get_or_create_attribute(
            target=p,
            name=bar_name,
            data={'a': 'b'},
            updated_by=self.u1
        )
        attr3 = ConfigAttribute.objects.get_or_create_attribute(
            target=p,
            name=foobar_name,
            data={'c': 'd'},
            updated_by=self.u2
        )
        self.assertEqual(ConfigAttribute.objects.count(), 3)

        url1 = reverse('configattribute-detail', kwargs={'pk': attr1.id})
        url2 = reverse('configattribute-detail', kwargs={'pk': attr2.id})
        url3 = reverse('configattribute-detail', kwargs={'pk': attr3.id})

        response = self.client.delete(url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        # Configuration Attirbute Name does not exist
        response = self.client.delete(url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(ConfigAttribute.objects.count(), 2)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        # Configuration Attirbute Name does not exist
        response = self.client.delete(url2, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(ConfigAttribute.objects.count(), 1)

        response = self.client.delete(url2, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(ConfigAttribute.objects.count(), 1)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.delete(url3, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(ConfigAttribute.objects.count(), 1)

        self.client.logout()
