import datetime
import json

import pytz

from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.devicetemplate.models import DeviceTemplate
from apps.org.models import Org, OrgMembership
from apps.physicaldevice.models import Device
from apps.property.models import GenericProperty
from apps.sensorgraph.models import SensorGraph, VariableTemplate
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.models import StreamData
from apps.utils.test_util import TestMixin
from apps.vartype.models import VarType

from ..models import *
from ..utils import *

user_model = get_user_model()


class ProjectAPITestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.projectTemplateTestSetup()

    def tearDown(self):
        GenericProperty.objects.all().delete()
        self.projectTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testInvalidId(self):
        p1 = Project.objects.create(name='Project 10', created_by=self.u1, org=self.o2)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        detail_url1 = reverse('project-detail', kwargs={'pk': 'bad-word'})
        resp = self.client.get(detail_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized[0], 'Project ID must be a UUID' )

    def testGetProject(self):
        """
        Ensure we can call GET on the org API.
        """
        url = reverse('project-list')

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        p1 = Project.objects.create(name='Project 10', created_by=self.u2, org=self.o2)
        p2 = Project.objects.create(name='Project 20', created_by=self.u3, org=self.o3)
        detail_url1 = reverse('project-detail', kwargs={'pk': str(p1.id)})
        detail_url2 = reverse('project-detail', kwargs={'pk': str(p2.id)})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        resp = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 6)

        resp = self.client.get(detail_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.get(detail_url2, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.get(detail_url1+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], str(p1.id))
        self.assertEqual(deserialized['name'], str(p1.name))
        self.assertEqual(deserialized['slug'], str(p1.slug))
        self.assertFalse('devices' in deserialized)

        self.client.logout()

        # Staff has access to all
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        resp = self.client.get(detail_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], str(p1.id))

        resp = self.client.get(detail_url2, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        resp = self.client.get(detail_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.get(detail_url2, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testPostProject(self):
        """
        Ensure we can call GPOSTET on the org API.
        """
        url = reverse('project-list')

        payload = {
            'name': 'Added by Staff',
            'org': self.o2.slug
        }
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        payload = {
            'name': 'With About',
            'about': 'Here is the desc',
            'org': self.o2.slug
        }
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(resp.content.decode())
        # Should default to default template
        self.assertEqual(deserialized['project_template'], self.pt1.slug)

        pt2 = ProjectTemplate.objects.create(name='Simple', org=self.o1, created_by=self.u1)
        payload = {
            'name': 'With project template',
            'project_template': pt2.slug,
            'org': self.o2.slug
        }
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['project_template'], pt2.slug)

        self.client.logout()

        payload = {
            'name': 'Added by Member',
            'org': self.o2.slug
        }
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.client.logout()

        payload = {
            'name': 'ERROR Non-member',
            'org': self.o2.slug
        }
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        membership = self.o2.register_user(self.u3, role='m1')
        membership.permissions['can_manage_org_and_projects'] = False
        membership.save()

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testPatchProject(self):
        """
        Ensure we can call GPOSTET on the org API.
        """
        p1 = Project.objects.create(name='Project 10', created_by=self.u2, org=self.o2)
        url = reverse('project-detail', kwargs={'pk': str(p1.id)})

        payload = {
            'name': 'Changed by Staff'
        }
        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.patch(url+'?staff=1', data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        p1 = Project.objects.get(pk=p1.id)
        self.assertEqual(p1.name, payload['name'])

        self.client.logout()

        payload = {
            'name': 'Changed by Member'
        }
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        p1 = Project.objects.get(pk=p1.id)
        self.assertEqual(p1.name, payload['name'])

        self.client.logout()

        payload = {
            'name': 'Non-member'
        }
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        membership = self.o2.register_user(self.u3, role='m1')
        membership.permissions['can_manage_org_and_projects'] = False
        membership.save()

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testGetProperties(self):
        p1 = Project.objects.create(name='Project 10', created_by=self.u2, org=self.o2)
        p2 = Project.objects.create(name='Project 20', created_by=self.u3, org=self.o3)
        GenericProperty.objects.create_int_property(slug=p1.slug,
                                                    created_by=self.u1,
                                                    name='prop1', value=4)
        GenericProperty.objects.create_str_property(slug=p1.slug,
                                                    created_by=self.u1,
                                                    name='prop2', value='4')
        GenericProperty.objects.create_bool_property(slug=p2.slug,
                                                     created_by=self.u1,
                                                     name='prop3', value=True)
        url = reverse('project-properties', kwargs={'pk': str(p1.id)})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(len(deserialized), 2)
        self.assertEqual(deserialized[0]['name'], 'prop1')
        self.assertEqual(deserialized[0]['type'], 'int')
        self.assertEqual(deserialized[0]['value'], 4)
        self.assertEqual(deserialized[1]['name'], 'prop2')
        self.assertEqual(deserialized[1]['type'], 'str')
        self.assertEqual(deserialized[1]['value'], '4')

        self.client.logout()

        # Staff has access to all
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(len(deserialized), 2)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

    def testPostProperties(self):
        p1 = Project.objects.create(name='Project 10', created_by=self.u2, org=self.o2)
        p2 = Project.objects.create(name='Project 20', created_by=self.u3, org=self.o3)
        url = reverse('project-new-property', kwargs={'pk': str(p1.id)})+'?staff=1'

        payload = {
            'name': 'NewProp1'
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        payload['int_value'] = 5
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        payload = {
            'name': 'NewProp2',
            'str_value': '6'
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        payload = {
            'name': 'NewProp3',
            'bool_value': True
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        qs = p1.get_properties_qs()
        self.assertEqual(qs.count(), 3)
        self.assertEqual(qs[0].value, 5)
        self.assertEqual(qs[1].value, '6')
        self.assertEqual(qs[2].value, True)

        payload = {
            'name': 'NewProp4',
            'int_value': 7,
            'bool_value': True
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        payload = {
            'name': 'NewProp5',
            'int_value': 7,
            'str_value': 'Foo',
            'bool_value': True
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.logout()

        # Staff has access to all
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        url = reverse('project-new-property', kwargs={'pk': str(p1.id)})

        payload = {
            'name': 'NewProp4',
            'bool_value': True
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        qs = p1.get_properties_qs()
        self.assertEqual(qs.count(), 4)
        p4 = qs.get(name='NewProp4')
        self.assertTrue(p4.value)

        payload = {
            'name': 'NewProp4',
            'bool_value': False
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        qs = p1.get_properties_qs()
        self.assertEqual(qs.count(), 4)
        p4 = qs.get(name='NewProp4')
        self.assertFalse(p4.value)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            'name': 'NewProp5',
            'bool_value': True
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

    def testFilter(self):
        url = reverse('project-list')

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        p1 = Project.objects.create(name='abc', created_by=self.u2, org=self.o2)
        p2 = Project.objects.create(name='cde', created_by=self.u2, org=self.o2)
        o3 = Org.objects.create_org(name='Org 3', created_by=self.u2)
        p3 = Project.objects.create(name='xyz', created_by=self.u2, org=o3)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)

        resp = self.client.get(url+'?org={}'.format(self.o2.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 3)

        resp = self.client.get(url+'?org={}'.format(o3.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['org'], o3.slug)

        resp = self.client.get(url+'?org__slug={}'.format(self.o2.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 3)

        resp = self.client.get(url+'?org__slug={}'.format(o3.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['org'], o3.slug)

        resp = self.client.get(url+'?slug={}'.format(p1.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['slug'], p1.slug)

        resp = self.client.get(url+'?name={}'.format(p2.name), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['slug'], p2.slug)
        self.assertEqual(deserialized['results'][0]['name'], p2.name)

        resp = self.client.get(url+'?name=c', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        GenericProperty.objects.create_int_property(slug=p1.slug,
                                                    created_by=self.u1,
                                                    name='prop1', value=4)
        GenericProperty.objects.create_str_property(slug=p1.slug,
                                                    created_by=self.u1,
                                                    name='prop2', value='4')
        GenericProperty.objects.create_int_property(slug=p2.slug,
                                                    created_by=self.u1,
                                                    name='prop1', value=5)

        resp = self.client.get(url + '?property=prop1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        resp = self.client.get(url + '?property=prop2', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        resp = self.client.get(url + '?property=prop1__4', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['slug'], p1.slug)

        resp = self.client.get(url + '?slug={}'.format(p1.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['slug'], p1.slug)
