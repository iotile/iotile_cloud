import datetime
import json

import dateutil.parser

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import dateparse, timezone
from django.utils.dateparse import parse_datetime

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.physicaldevice.models import Device
from apps.projecttemplate.models import ProjectTemplate
from apps.streamdata.models import StreamData
from apps.utils.gid.convert import *
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import str_utc
from apps.vartype.models import *

from ..helpers import *
from ..models import *

user_model = get_user_model()


class StreamVariableTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.projectTestSetup()

    def tearDown(self):
        StreamVariable.objects.all().delete()
        self.projectTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testVariableId(self):
        self.assertEqual(formatted_gvid('0001', '0001'), 'v--0000-0001--0001')
        self.assertEqual(formatted_gvid('0000-0001', '0001'), 'v--0000-0001--0001')

        self.assertEqual(int2vid(1), '0001')
        self.assertEqual(int2vid(1024), '0400')

    def testBasicStreamVariableObject(self):
        v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, lid=1, created_by=self.u2
        )
        self.assertEqual(v1.formatted_lid, '0001')
        expected = '{0}--0001'.format(self.p1.formatted_gid)
        self.assertEqual(v1.formatted_gid, expected)
        self.assertEqual(v1.slug, 'v--{0}'.format(expected))
        self.assertEqual(str(v1), 'v--{0} (Var A)'.format(expected))
        '''
        self.assertEqual(s1.get_absolute_url(),
                     '/org/{0}/project/{1}/stream/{2}/'.format(self.o2.slug, str(self.p1.id), str(s1.id)))
        '''

    def testManagerCreate(self):
        s = StreamVariable.objects.create_variable(
            name='Var1', lid=1, project=self.p1, created_by=self.u2
        )
        self.assertIsNotNone(s)
        self.assertEqual(s.org, self.p1.org)
        s = StreamVariable.objects.create_variable(
            name='Var2', project=self.p1, created_by=self.u2, lid=2
        )

        with self.assertRaises(AssertionError):
            s = StreamVariable.objects.create_variable(
                name='Var3', project=self.p1, created_by=self.u2, lid=3, foo=1
            )

    def testHasAccess(self):
        s1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, lid=1, created_by=self.u2
        )
        s2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p2, created_by=self.u3, lid=2,
        )
        self.assertTrue(s1.has_access(self.u1))
        self.assertTrue(s1.has_access(self.u2))
        self.assertFalse(s1.has_access(self.u3))
        self.assertTrue(s2.has_access(self.u1))
        self.assertFalse(s2.has_access(self.u2))
        self.assertTrue(s2.has_access(self.u3))
        self.assertEqual(StreamVariable.objects.user_variables_qs(self.u1).count(), 0)
        self.assertEqual(StreamVariable.objects.user_variables_qs(self.u2).count(), 1)
        self.assertEqual(StreamVariable.objects.user_variables_qs(self.u3).count(), 1)
        self.assertEqual(StreamVariable.objects.user_variables_qs(self.u2, self.p1).count(), 1)
        self.assertEqual(StreamVariable.objects.user_variables_qs(self.u3, self.p2).count(), 1)
        self.assertEqual(StreamVariable.objects.user_variables_qs(self.u2, self.p2).count(), 0)
        self.o2.register_user(self.u3)
        self.assertEqual(StreamVariable.objects.user_variables_qs(self.u3).count(), 2)
        self.assertEqual(StreamVariable.objects.user_variables_qs(self.u3, self.p1).count(), 1)

    def testAccess(self):
        StreamVariable.objects.create_variable(
            name='A', project=self.p1, lid=1, created_by=self.u2
        )
        StreamVariable.objects.create_variable(
            name='B', project=self.p1, lid=2, created_by=self.u2
        )
        qs2 = StreamVariable.objects.user_variables_qs(self.u2)
        qs3 = StreamVariable.objects.user_variables_qs(self.u3)
        self.assertEqual(qs2.count(), 2)
        self.assertEqual(qs3.count(), 0)

        self.o2.register_user(self.u3)
        qs3 = StreamVariable.objects.user_variables_qs(self.u3)
        self.assertEqual(qs3.count(), 2)

    def testStreamDelete(self):
        """
        dt2 = DeviceTemplate.objects.create(name='Device 1', org=self.o1,
                                            released_on=datetime.datetime.utcnow(),
                                            created_by=self.u1)
        """

        pd1 = Device.objects.create(id=1, project=self.p1, created_by=self.u2)
        v1 = StreamVariable.objects.create_variable(
            name='A', project=self.p1, lid=1, created_by=self.u2
        )
        v2 = StreamVariable.objects.create_variable(
            name='B', project=self.p1, lid=2, created_by=self.u2
        )
        s1 = StreamId.objects.create_stream(
            project=self.p1, variable=v1, device=pd1, created_by=self.u2
        )
        s2 = StreamId.objects.create_stream(
            project=self.p1, variable=v2, device=pd1, created_by=self.u2
        )
        db1 = DataBlock.objects.create(org=self.o1, title='test', device=pd1, block=1, created_by=self.u1)
        slug = formatted_gsid(pid=self.p1.formatted_gid, did=db1.formatted_gid, vid=v2.formatted_lid)
        s3 = StreamId.objects.create(
            org=self.o1, project=None, block=db1, variable=v2, device=pd1, created_by=self.u2, slug=slug
        )
        StreamData.objects.create(
            stream_slug=s2.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=s3.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=7
        )

        self.assertEqual(StreamData.objects.count(), 2)
        self.assertEqual(StreamVariable.objects.count(), 2)
        self.assertEqual(StreamId.objects.count(), 3)
        v2.delete()
        self.assertEqual(StreamVariable.objects.count(), 1)
        self.assertEqual(StreamId.objects.count(), 2)
        self.assertEqual(StreamData.objects.count(), 1)


class StreamVariableAPITests(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testPost(self):
        url = '/api/v1/variable/'
        payload = {
            'name': 'foo',
            'project': str(self.p1.id),
            'lid': 1
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.client.logout()

    def testPostPatchUnits(self):
        var_type = VarType.objects.create(name='Volume', created_by=self.u1)
        gallons = VarTypeInputUnit.objects.create(unit_full='Gallons', m=3, var_type=var_type, created_by=self.u1)
        liters = VarTypeInputUnit.objects.create(unit_full='Liters', m=2, var_type=var_type, created_by=self.u1)
        url = reverse('streamvariable-list')
        payload = {
            'name': 'foo',
            'project': str(self.p1.id),
            'lid': 1,
            'var_type': var_type.slug,
            'input_unit': gallons.slug
        }

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        url = reverse('streamvariable-detail', kwargs={'slug': 'v--{0}--0001'.format(self.p1.formatted_gid)})
        response = self.client.get(url, format='json')
        deserialized = json.loads(response.content.decode())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(deserialized['input_unit']['unit_full'], 'Gallons')
        self.assertEqual(deserialized['units'], '')

        payload = {
            'input_unit': liters.slug
        }
        response = self.client.patch(url, payload, format='json')
        deserialized = json.loads(response.content.decode())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(deserialized['input_unit']['unit_full'], 'Liters')

        self.client.logout()

    def testGetVariableWithSlug(self):
        """
        Ensure we can call GET on the org API.
        """
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, lid=1, created_by=self.u2
        )

        for ok_slug in ['v--0002--0001', 'v--0000-0002--0001']:
            url = reverse('streamvariable-detail', kwargs={'slug': ok_slug})

            resp = self.client.get(url, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            deserialized = json.loads(resp.content.decode())
            self.assertEqual(deserialized['slug'], str(v1.slug))

        for fail_slug in ['0001', '0002--0001', str(v1.id)]:
            url = reverse('streamvariable-detail', kwargs={'slug': fail_slug})

            resp = self.client.get(url, format='json')
            self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def testOrgFilter(self):
        v1 = StreamVariable.objects.create_variable(
            name='Project Variable 1', project=self.p1, lid=1, created_by=self.u2
        )
        v2 = StreamVariable.objects.create_variable(
            name='Project Variable 2', project=self.p1, lid=2, created_by=self.u2
        )
        v3 = StreamVariable.objects.create_variable(
            name='Other Project Variable', project=self.p2, lid=1, created_by=self.u3
        )
        Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        Device.objects.create_device(project=self.p1, label='d2', template=self.dt1, created_by=self.u2)
        v3 = StreamVariable.objects.create_system_variable(
            name='Template Variable', lid=2, created_by=self.u2
        )

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        url = reverse('streamvariable-list') + '?org={0}'.format('foo-bar')
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        url = reverse('streamvariable-list') + '?org={0}'.format(self.o2.slug)
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        url = reverse('streamvariable-list') + '?org={0}'.format(self.o3.slug)
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        url = reverse('streamvariable-list') + '?org={0}'.format(self.o3.slug)
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

    def testProjectFilter(self):
        v1 = StreamVariable.objects.create_variable(
            name='Project Variable 1', project=self.p1, lid=1, created_by=self.u2
        )
        v2 = StreamVariable.objects.create_variable(
            name='Project Variable 2', project=self.p1, lid=2, created_by=self.u2
        )
        v3 = StreamVariable.objects.create_variable(
            name='Other Project Variable', project=self.p2, lid=1, created_by=self.u3
        )
        Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        Device.objects.create_device(project=self.p1, label='d2', template=self.dt1, created_by=self.u2)
        v3 = StreamVariable.objects.create_system_variable(
            name='Template Variable', lid=2, created_by=self.u2
        )

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        url = reverse('streamvariable-list') + '?project={0}'.format('foo-bar')
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        url = reverse('streamvariable-list') + '?project={0}'.format(self.p1.id)
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        url = reverse('streamvariable-list') + '?project={0}'.format(self.p2.id)
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        url = reverse('streamvariable-list') + '?project={0}'.format(self.p2.id)
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

    def testIncludeTemplateVariables(self):
        v1 = StreamVariable.objects.create_variable(
            name='Project Variable', project=self.p1, lid=1, created_by=self.u2
        )
        v2 = StreamVariable.objects.create_variable(
            name='Other Project Variable', project=self.p2, lid=1, created_by=self.u2
        )
        Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        Device.objects.create_device(project=self.p1, label='d2', template=self.dt1, created_by=self.u2)
        v3 = StreamVariable.objects.create_system_variable(
            name='Template Variable', lid=0x1000, created_by=self.u2
        )
        self.p1.project_template = self.pt1
        self.p1.save()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        url_without_templates = reverse('streamvariable-list') + '?project={0}'.format(self.p1.id)
        url_with_templates = url_without_templates + '&include_templates=1'

        resp = self.client.get(url_without_templates, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        rv1 = deserialized['results'][0]
        self.assertEqual(rv1['slug'], v1.slug)

        resp = self.client.get(url_with_templates, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 3)

        self.client.logout()

    def testPatchMdo(self):
        """
        Ensure we can modify MDO
        """

        v1 = StreamVariable.objects.create_variable(
            name='Project Variable', project=self.p1, lid=1, created_by=self.u2
        )
        url = reverse('streamvariable-detail', kwargs={'slug': v1.slug})

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        data = {
            'multiplication_factor':10,
            'division_factor': 20,
            'offset': 5.0,
            'mdo_label': 'Pulse/Unit',
            'units': 'Gallons'
        }

        resp = self.client.patch(url, data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        v2 = StreamVariable.objects.get(slug=v1.slug)
        self.assertEqual(v2.multiplication_factor, 10)
        self.assertEqual(v2.division_factor, 20)
        self.assertEqual(v2.offset, 5.0)
        self.assertEqual(v2.mdo_label, 'Pulse/Unit')
        self.assertEqual(v2.units, 'Gallons')

        self.client.logout()
