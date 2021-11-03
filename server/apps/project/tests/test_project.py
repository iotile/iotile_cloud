import json
import datetime
import pytz
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from rest_framework import status

from apps.utils.test_util import TestMixin
from apps.org.models import OrgMembership, Org
from apps.physicaldevice.models import Device
from apps.devicetemplate.models import DeviceTemplate
from apps.vartype.models import VarType
from apps.sensorgraph.models import SensorGraph, VariableTemplate
from apps.stream.models import StreamVariable, StreamId
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.streamnote.models import StreamNote

from ..models import *
from ..utils import *

user_model = get_user_model()


class ProjectTestCase(TestMixin, TestCase):
    """
    Fixure includes:
    """
    #fixtures = ['testdb_main.json']

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.pt1 = ProjectTemplate.objects.create(name='Default Template', org=self.o1, created_by=self.u1)

    def tearDown(self):
        StreamVariable.objects.all().delete()
        Project.objects.all().delete()
        ProjectTemplate.objects.all().delete()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasicPhysicalDeviceObject(self):
        p1 = Project.objects.create(name='Project 1', created_by=self.u2, org=self.o2)
        self.assertEqual(str(p1), '{0} - {1}'.format(p1.org.name, p1.name))

    def testObjectAccess(self):
        p1 = Project.objects.create(name='Project 1', created_by=self.u2, org=self.o2)
        p2 = Project.objects.create(name='Project 2', created_by=self.u3, org=self.o3)
        self.assertTrue(p1.has_access(self.u1))
        self.assertTrue(p1.has_access(self.u2))
        self.assertFalse(p1.has_access(self.u3))
        self.assertTrue(p2.has_access(self.u1))
        self.assertFalse(p2.has_access(self.u2))
        self.assertTrue(p2.has_access(self.u3))

    def testProjectGid(self):
        p1 = Project.objects.create(name='Project 1', created_by=self.u2, org=self.o2)
        gid = p1.gid
        self.assertTrue(gid > 0)
        p2 = Project.objects.create(name='Project 2', created_by=self.u2, org=self.o2)
        self.assertTrue(p2.gid == gid + 1)
        p1.delete()
        p3 = Project.objects.create(name='Project 3', created_by=self.u2, org=self.o2)
        self.assertTrue(p3.gid == gid + 2)
        self.assertEqual(p3.formatted_gid, '0000-000{}'.format(p3.gid))
        self.assertEqual(p3.slug, 'p--0000-000{}'.format(p3.gid))

    def testGetProject(self):
        """
        Ensure we can call GET project page
        """

        p1 = Project.objects.create(name='Project 1', created_by=self.u2, org=self.o2)

        detail_url = reverse('org:project:detail', kwargs={'org_slug':self.o2.slug, 'pk': p1.id})
        all_table_url = reverse('org:project:streamid-list', kwargs={'org_slug':self.o2.slug, 'pk': p1.id})

        resp = self.client.get(detail_url, format='json')
        self.assertRedirects(resp, expected_url='/account/login/?next='+detail_url, status_code=302, target_status_code=200)
        resp = self.client.get(all_table_url, format='json')
        self.assertRedirects(resp, expected_url='/account/login/?next='+all_table_url, status_code=302, target_status_code=200)

        self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.get(all_table_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()
        self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(all_table_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testProjectCreate(self):
        project_name1 = 'New Project 1'
        p1 = Project.objects.create(name=project_name1, created_by=self.u3, org=self.o3)

        url = reverse('org:project:new', kwargs={'org_slug': self.o2.slug})
        payload = {'new_name': project_name1}

        self.assertEqual(Project.objects.count(), 2)

        resp = self.client.post(url, payload)
        self.assertRedirects(resp, expected_url='/account/login/?next='+url, status_code=302, target_status_code=200)

        self.assertEqual(Project.objects.count(), 2)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertEqual(ok, True)

        resp = self.client.post(url, payload)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)

        self.assertEqual(Project.objects.count(), 3)
        project = Project.objects.first()
        self.assertEqual(project.name, payload['new_name'])

        resp = self.client.post(url, payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertEqual(Project.objects.count(), 3)

        payload = {'new_name': project_name1 + 'diff'}
        resp = self.client.post(url, payload)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)

        self.assertEqual(Project.objects.count(), 4)

        self.client.logout()

    def testDeleteProject(self):
        """
        Ensure we can delete a project
        """

        p1 = Project.objects.create(name='Project 1', created_by=self.u2, org=self.o2)

        project_url = reverse('org:project:detail', kwargs={'org_slug':self.o2.slug, 'pk': p1.id})
        edit_url = reverse('org:project:edit', kwargs={'org_slug':self.o2.slug, 'pk': p1.id})
        delete_url = reverse('org:project:delete', kwargs={'org_slug':self.o2.slug, 'pk': p1.id})

        resp = self.client.get(project_url, format='json')
        self.assertRedirects(resp, expected_url='/account/login/?next='+project_url, status_code=302, target_status_code=200)
        resp = self.client.get(edit_url, format='json')
        self.assertRedirects(resp, expected_url='/account/login/?next='+edit_url, status_code=302, target_status_code=200)
        resp = self.client.get(delete_url, format='json')
        self.assertRedirects(resp, expected_url='/account/login/?next='+delete_url, status_code=302, target_status_code=200)

        self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(project_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(edit_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(delete_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        dt = DeviceTemplate.objects.create_template(external_sku='Device 1',
                                                    released_on=datetime.datetime.utcnow(),
                                                    created_by=self.u2, org=self.o2)
        d1 = Device.objects.create_device(project=p1, label='d1', template=dt, created_by=self.u2)
        d2 = Device.objects.create_device(project=p1, label='d2', template=dt, created_by=self.u3)
        v1 = StreamVariable.objects.create_variable(
            name='Var A', project=p1, created_by=self.u2, lid=1,
        )
        v2 = StreamVariable.objects.create_variable(
            name='Var B', project=p1, created_by=self.u3, lid=2,
        )
        StreamId.objects.create_after_new_device(d1)
        StreamId.objects.create_after_new_device(d2)
        s1 = StreamId.objects.filter(variable=v1).first()
        s2 = StreamId.objects.filter(variable=v2).first()
        sd1 = StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=datetime.datetime.now(pytz.utc),
            int_value=5,
            streamer_local_id=5
        )
        sd2 = StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=datetime.datetime.now(pytz.utc),
            int_value=5,
            streamer_local_id=6
        )
        sed1 = StreamEventData.objects.create(
            timestamp=datetime.datetime.now(pytz.utc),
            device_timestamp=42,
            stream_slug=s2.slug,
            streamer_local_id=42,
            extra_data={'value': 42},
        )
        sn1 = StreamNote.objects.create(
            target_slug=p1.slug,
            timestamp=datetime.datetime.now(pytz.utc),
            note='msg',
            created_by=self.u2,
        )
        self.assertTrue(Project.objects.filter(id=p1.id).exists())
        self.assertEqual(Device.objects.filter(project=p1.id).count(), 2)
        self.assertEqual(StreamVariable.objects.filter(project=p1.id).count(), 2)
        self.assertEqual(StreamId.objects.filter(project=p1.id).count(), 4)
        self.assertEqual(StreamData.objects.filter(project_slug=p1.slug).count(), 2)
        self.assertEqual(StreamEventData.objects.filter(project_slug=p1.slug).count(), 1)
        self.assertEqual(StreamNote.objects.filter(target_slug=p1.slug).count(), 1)

        resp = self.client.get(edit_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertContains(resp, "Want to delete the project?")
        self.assertContains(resp, "Devices :")
        self.assertContains(resp, str(d1.slug))
        self.assertContains(resp, str(d2.slug))

        d1.delete()
        d2.delete()
        self.assertTrue(Project.objects.filter(id=p1.id).exists())
        self.assertEqual(Device.objects.filter(project=p1.id).count(), 0)
        self.assertEqual(StreamVariable.objects.filter(project=p1.id).count(), 2)
        self.assertEqual(StreamId.objects.filter(project=p1.id).count(), 0)
        self.assertEqual(StreamData.objects.filter(project_slug=p1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(project_slug=p1.slug).count(), 0)
        self.assertEqual(StreamNote.objects.filter(target_slug=p1.slug).count(), 1)

        resp = self.client.get(edit_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotContains(resp, "Want to delete the project?")
        self.assertNotContains(resp, "Devices :")
        self.assertContains(resp, "Delete Project")

        resp = self.client.get(delete_url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertContains(resp, str(p1.name))
        self.assertContains(resp, str(p1.org))
        self.assertContains(resp, "Project Variables: {}".format(StreamVariable.objects.filter(project=p1.id).count()))
        self.assertContains(resp, "Streams: {}".format(StreamId.objects.filter(project=p1.id).count()))
        self.assertContains(resp, "Stream Data: {}".format(StreamData.objects.filter(project_slug=p1.slug).count()))
        self.assertContains(resp, "Stream Events: {}".format(StreamEventData.objects.filter(project_slug=p1.slug).count()))
        self.assertContains(resp, "Stream Notes: {}".format(StreamNote.objects.filter(target_slug=p1.slug).count()))        
        self.assertContains(resp, "Project data, once deleted, CANNOT be recovered.")
        # If name is incorrect, nothing is deleted
        resp = self.client.post(delete_url, data={"project_name": "sdkfnb;dkfnbw"})

        self.assertTrue(Project.objects.filter(id=p1.id).exists())
        self.assertEqual(Device.objects.filter(project=p1.id).count(), 0)
        self.assertEqual(StreamVariable.objects.filter(project=p1.id).count(), 2)
        self.assertEqual(StreamId.objects.filter(project=p1.id).count(), 0)
        self.assertEqual(StreamData.objects.filter(project_slug=p1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(project_slug=p1.slug).count(), 0)
        self.assertEqual(StreamNote.objects.filter(target_slug=p1.slug).count(), 1)

        p2 = Project.objects.create(name='Project 2', created_by=self.u2, org=self.o2)
        # If name is incorrect, nothing is deleted
        resp = self.client.post(delete_url, data={"project_name": p2.name})

        self.assertTrue(Project.objects.filter(id=p1.id).exists())
        self.assertTrue(Project.objects.filter(id=p2.id).exists())
        self.assertEqual(Device.objects.filter(project=p1.id).count(), 0)
        self.assertEqual(StreamVariable.objects.filter(project=p1.id).count(), 2)
        self.assertEqual(StreamId.objects.filter(project=p1.id).count(), 0)
        self.assertEqual(StreamData.objects.filter(project_slug=p1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(project_slug=p1.slug).count(), 0)
        self.assertEqual(StreamNote.objects.filter(target_slug=p1.slug).count(), 1)

        resp = self.client.get(delete_url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertContains(resp, str(p1.name))
        self.assertContains(resp, str(p1.org))
        self.assertContains(resp, "Project Variables: {}".format(StreamVariable.objects.filter(project=p1.id).count()))
        self.assertContains(resp, "Streams: {}".format(StreamId.objects.filter(project=p1.id).count()))
        self.assertContains(resp, "Stream Data: {}".format(StreamData.objects.filter(project_slug=p1.slug).count()))
        self.assertContains(resp, "Project data, once deleted, CANNOT be recovered.")
        resp = self.client.post(delete_url, data={"project_name": str(p1.name)})

        self.assertFalse(Project.objects.filter(id=p1.id).exists())
        self.assertEqual(Device.objects.filter(project=p1.id).count(), 0)
        self.assertEqual(StreamVariable.objects.filter(project=p1.id).count(), 0)
        self.assertEqual(StreamId.objects.filter(project=p1.id).count(), 0)
        self.assertEqual(StreamData.objects.filter(project_slug=p1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(project_slug=p1.slug).count(), 0)
        self.assertEqual(StreamNote.objects.filter(target_slug=p1.slug).count(), 0)

        resp = self.client.get(edit_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

    def testProjectPages(self):
        """
        Ensure we can call GET project page
        """
        p1 = Project.objects.create(name='Project 1', created_by=self.u2, org=self.o2)
        self.o2.de_register_user(self.u3, delete_obj=True)
        membership = self.o2.register_user(self.u3, role='m1')
        membership.permissions['can_access_classic'] = True
        membership.permissions['can_modify_device'] = True
        membership.save()

        detail_url = reverse('org:project:detail', kwargs={'org_slug': self.o2.slug, 'pk': p1.id})
        all_table_url = reverse('org:project:streamid-list', kwargs={'org_slug': self.o2.slug, 'pk': p1.id})
        var_url = reverse('org:project:var-list', kwargs={'org_slug': self.o2.slug, 'project_id': p1.id})
        devices_url = reverse('org:project:device:list', kwargs={'org_slug': self.o2.slug, 'project_id': p1.id})

        self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(self.o2.has_permission(self.u3, 'can_access_classic'))
        self.assertTrue(self.o2.has_permission(self.u3, 'can_modify_device'))

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(all_table_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(var_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(devices_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testWriteAccessProject(self):
        """
        Ensure only admins can delete and edit
        """

        p1 = Project.objects.create(name='Project 1', created_by=self.u2, org=self.o2)

        edit_url = reverse('org:project:edit', kwargs={'org_slug':self.o2.slug, 'pk': p1.id})
        delete_url = reverse('org:project:delete', kwargs={'org_slug':self.o2.slug, 'pk': p1.id})

        self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(edit_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(delete_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        delete_url = reverse('org:project:delete', kwargs={'org_slug':self.o2.slug, 'pk': p1.id})
        self.o2.register_user(self.u3)
        self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.get(edit_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)

        self.assertEqual(Project.objects.count(), 2)
        resp = self.client.get(delete_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        resp = self.client.post(delete_url, data={"project_name": p1.name})
        self.assertEqual(Project.objects.count(), 2)

        self.client.logout()

    def test_illegal_project(self):
        id = 'b5f12c71-5446-42a0-95cf-c345afe1d433' #illegal ID
        detail_url = reverse('org:project:detail', kwargs={'org_slug': self.o2.slug, 'pk': id})
        all_table_url = reverse('org:project:streamid-list', kwargs={'org_slug': self.o2.slug, 'pk': id})
        var_url = reverse('org:project:var-list', kwargs={'org_slug': self.o2.slug, 'project_id': id})
        devices_url = reverse('org:project:device:list', kwargs={'org_slug': self.o2.slug, 'project_id': id})

        self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.get(all_table_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.get(var_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.get(devices_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

