import json
import datetime
import pytz
from django.contrib.auth import get_user_model

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin
from apps.org.models import OrgMembership, Org
from apps.physicaldevice.models import Device
from apps.devicetemplate.models import DeviceTemplate
from apps.vartype.models import VarType
from apps.sensorgraph.models import SensorGraph, VariableTemplate
from apps.stream.models import StreamVariable, StreamId
from apps.streamdata.models import StreamData
from apps.property.models import GenericProperty

from ..models import *
from ..utils import *

user_model = get_user_model()


class ProjectCloneCase(TestMixin, APITestCase):
    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.projectTemplateTestSetup()

    def tearDown(self):
        self.projectTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testGetMasterProject(self):
        self.assertEqual(ProjectTemplate.objects.count(), 2)
        self.assertEqual(Project.objects.count(), 4)
        self.assertTrue(self.pt1_project.is_template)
        self.assertFalse(self.p1.is_template)
        self.assertFalse(self.p2.is_template)
        master1 = Project.objects.master_project_for_template(self.pt1)
        self.assertEqual(master1.project_template, self.pt1)
        self.assertTrue(master1.is_template)

    def testClone(self):

        count = Project.objects.count()
        project_dst, msg = create_project_from_template(
            created_by=self.u2,
            project_name='My New Project',
            org=self.o2,
            project_template=self.pt1
        )
        self.assertIsNotNone(project_dst)
        self.assertIsNotNone(msg)
        self.assertEqual(Project.objects.count(), count + 1)

        self.assertEqual(StreamVariable.objects.count(), 3)
        self.assertEqual(project_dst.variables.count(), 1)

    def testCloneLongName(self):

        long_name = 'very very very very very very very very very very very very long, Illegal Project name'

        count = Project.objects.count()
        project_dst, msg = create_project_from_template(
            created_by=self.u2,
            project_name=long_name,
            org=self.o2,
            project_template=self.pt1
        )
        self.assertIsNone(project_dst)
        self.assertIsNotNone(msg)
        self.assertEqual(Project.objects.count(), count)

    def testPostProjectWithDevices(self):
        """
        Ensure we can create a new project for a given devie
        """

        long_name = 'very very very very very very very very very very very very long, Illegal Project name'
        url = reverse('project-new')

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            'name': long_name,
            'org': self.o2.slug
        }

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        payload = {
            'name': 'Project name',
            'org': self.o2.slug
        }

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        deserialized = json.loads(resp.content.decode())
        project = Project.objects.get(pk=deserialized['id'])

        dt1 = DeviceTemplate.objects.create(external_sku='Device 1', org=self.o1,
                                            released_on=datetime.datetime.utcnow(),
                                            created_by=self.u1)

        sg = SensorGraph.objects.create(name='SG2', project_template=self.pt1, created_by=self.u1)
        pd1 = Device.objects.create(template=dt1, created_by=self.u1, sg=sg)

        payload = {
            'name': long_name,
            'org': self.o2.slug,
            'device': pd1.slug
        }

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        payload = {
            'name': 'Good Name',
            'org': self.o2.slug,
            'device': pd1.slug
        }
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        project = Project.objects.get(name=payload['name'])
        self.assertIsNotNone(project)
        self.assertEqual(StreamVariable.objects.count(), 2)
        self.assertEqual(project.variables.count(), 0)

        sg = SensorGraph.objects.create(name='SG1', project_template=self.pt1, created_by=self.u1)
        pd2 = Device.objects.create(template=dt1, sg=sg, created_by=self.u1)
        payload = {
            'name': 'From SG',
            'org': self.o2.slug,
            'device': pd2.slug
        }

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        project = Project.objects.get(name=payload['name'])
        self.assertIsNotNone(project)
        self.assertEqual(StreamVariable.objects.count(), 2)
        self.assertEqual(project.variables.count(), 0)

    def testPostProjectWithNewSensorGraphTemplateVariables(self):
        """
        Ensure we can create a new project for a given devie
        """

        name = 'the new project'
        url = reverse('project-new')

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        water_volume = VarType.objects.create(
            name='Water Meter Volume',
            storage_units_full='Liters',
            created_by=self.u1
        )
        dt1 = DeviceTemplate.objects.create(external_sku='Device 1', org=self.o1,
                                            released_on=datetime.datetime.utcnow(),
                                            created_by=self.u1)
        sg = SensorGraph.objects.create(name='SG10', project_template=self.pt1, created_by=self.u1)
        VariableTemplate.objects.create(
            label='IO 1',
            sg=sg,
            lid_hex='5001',
            var_type=water_volume,
            created_by=self.u1
        )
        VariableTemplate.objects.create(
            label='IO 2',
            sg=sg,
            lid_hex='5002',
            var_type=water_volume,
            created_by=self.u1
        )
        pd2 = Device.objects.create(template=dt1, sg=sg, created_by=self.u1)
        payload = {
            'name': 'From SG',
            'org': self.o2.slug,
            'device': pd2.slug
        }

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(resp.content.decode())
        project = Project.objects.get(id=deserialized['id'])
        vars = StreamVariable.objects.filter(project=project)
        self.assertEqual(vars.count(), 2)


