import json

from django.contrib.auth import get_user_model
from django.test import override_settings

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.property.models import GenericPropertyOrgEnum, GenericPropertyOrgTemplate
from apps.utils.test_util import TestMixin
from apps.vartype.models import VarType

from ..models import DisplayWidgetTemplate, SensorGraph, VariableTemplate

user_model = get_user_model()


class SensorGraphAPITestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()

    def tearDown(self):
        self.projectTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testPostGet(self):
        url = reverse('sensorgraph-list')
        payload = {
            'name': 'foo',
            'app_tag': 1027,
            'app_major_version': 2,
            'major_version': 3,
            'patch_version': 1,
            'org': str(self.o1.slug)
        }
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['app_tag'], 1027)
        self.assertEqual(deserialized['app_version'], 'v2.0')
        self.assertEqual(deserialized['version'], 'v3.0.1')

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testGet(self):
        vt = VarType.objects.create(name="test vartype",
                                    storage_units_full="test unit",
                                    created_by=self.u1)
        sg1 = SensorGraph.objects.create_graph(name='SG 1', created_by=self.u1, org=self.o1)

        variable = VariableTemplate.objects.create(sg=sg1, created_by=self.u1, label='Var1', var_type=vt)
        widget = DisplayWidgetTemplate.objects.create(sg=sg1, created_by=self.u1, label='Widget 1')

        url = reverse('sensorgraph-detail', kwargs={'slug': str(sg1.slug)})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(len(deserialized['display_widget_templates']), 1)
        self.assertEqual(deserialized['display_widget_templates'][0]['label'], widget.label)
        self.assertEqual(len(deserialized['variable_templates']), 1)
        self.assertEqual(deserialized['variable_templates'][0]['label'], variable.label)

        self.client.logout()

    @override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    def testGetProperties(self):
        p1 = GenericPropertyOrgTemplate.objects.create(name='F1', org=self.o2, created_by=self.u1, type='enum')
        p2 = GenericPropertyOrgTemplate.objects.create(name='F2', org=self.o3, created_by=self.u1, type='str')
        p3 = GenericPropertyOrgTemplate.objects.create(name='F3', org=self.o3, created_by=self.u1)
        p4 = GenericPropertyOrgTemplate.objects.create(name='F4', org=self.o1, created_by=self.u1)
        GenericPropertyOrgEnum.objects.create(value='a', org=self.o2, created_by=self.u2, template=p1)
        GenericPropertyOrgEnum.objects.create(value='b', org=self.o2, created_by=self.u2, template=p1)
        self.assertEqual(GenericPropertyOrgTemplate.objects.count(), 4)
        self.assertEqual(p1.enums.count(), 2)

        sg1 = SensorGraph.objects.create_graph(name='SG 1', created_by=self.u1, org=self.o1)
        sg1.org_properties.add(p1)
        sg1.org_properties.add(p2)
        sg1.org_properties.add(p3)
        self.assertEqual(sg1.org_properties.count(), 3)

        url = reverse('sensorgraph-property', kwargs={'slug': str(sg1.slug)})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        sg1.org_properties.add(p4)
        self.assertEqual(p4.org.id, sg1.org.id)
        self.assertEqual(sg1.org_properties.count(), 4)
        self.assertEqual(sg1.org_properties.filter(org=sg1.org).count(), 1)
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['org'], self.o1.slug)
        self.assertEqual(deserialized['results'][0]['name'], p4.name)

        resp = self.client.get(url+'?org={}'.format(self.o2.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['org'], self.o2.slug)
        self.assertEqual(deserialized['results'][0]['name'], p1.name)

        resp = self.client.get(url+'?org={}'.format(self.o3.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)
        self.assertEqual(deserialized['results'][0]['org'], self.o3.slug)
        self.assertEqual(deserialized['results'][1]['org'], self.o3.slug)

        self.client.logout()

    def testAddOrgProperties(self):
        p1 = GenericPropertyOrgTemplate.objects.create(name='F1', org=self.o2, created_by=self.u1, type='enum')
        p2 = GenericPropertyOrgTemplate.objects.create(name='F2', org=self.o3, created_by=self.u1, type='str')
        p3 = GenericPropertyOrgTemplate.objects.create(name='F3', org=self.o3, created_by=self.u1)
        p4 = GenericPropertyOrgTemplate.objects.create(name='F4', org=self.o1, created_by=self.u1)
        GenericPropertyOrgEnum.objects.create(value='a', org=self.o2, created_by=self.u2, template=p1)
        GenericPropertyOrgEnum.objects.create(value='b', org=self.o2, created_by=self.u2, template=p1)
        self.assertEqual(GenericPropertyOrgTemplate.objects.count(), 4)
        self.assertEqual(p1.enums.count(), 2)

        sg1 = SensorGraph.objects.create_graph(name='SG 1', created_by=self.u1, org=self.o1)
        self.assertEqual(sg1.org_properties.count(), 0)

        url = reverse('sensorgraph-property', kwargs={'slug': str(sg1.slug)})

        payload = { 'id': p1.id }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.u1.is_admin)

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(sg1.org_properties.count(), 1)

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(sg1.org_properties.count(), 1)

        payload = { 'id': 100 }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        payload = { 'id': p2.id }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(sg1.org_properties.count(), 2)

        self.client.logout()
