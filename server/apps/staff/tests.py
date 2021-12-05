
import datetime
import json
from unittest import mock

import dateutil.parser

from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from rest_framework import status

from apps.deviceauth.models import DeviceKey
from apps.devicetemplate.models import DeviceTemplate
from apps.org.models import Org
from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.property.models import GenericProperty
from apps.sensorgraph.models import SensorGraph
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.utils.gid.convert import int16gid
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import str_utc

user_model = get_user_model()


class StaffTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

        self.admin = user_model.objects.create_superuser(username='admin', email='admin@acme.com', password='pass')
        self.admin.is_active = True
        self.admin.save()
        self.assertTrue(self.admin.is_admin)
        self.assertTrue(self.admin.is_staff)

        self.staff = user_model.objects.create_user(username='staff', email='staff@acme.com', password='pass')
        self.staff.is_active = True
        self.staff.is_admin = False
        self.staff.is_staff = True
        self.staff.save()

        self.user = user_model.objects.create_user(username='user', email='user@acme.com', password='pass')
        self.user.is_active = True
        self.user.is_admin = False
        self.user.is_staff = False
        self.user.save()

    def tearDown(self):
        StreamId.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    @mock.patch('apps.staff.views.WorkerStats')
    def testAccessControls(self, mock_worker_stats):
        mock_worker_stats.return_value = {}

        url_list = [
            reverse('staff:home'),
            reverse('staff:map'),
            reverse('staff:ops-status'),
            reverse('staff:streams'),
            reverse('staff:user-create'),
            reverse('staff:iotile-batch'),
            reverse('staff:gateway'),
            reverse('staff:sg-matrix'),
        ]
        for url in url_list:
            response = self.client.get(url)
            self.assertRedirects(response, '/account/login/?next={0}'.format(url))

            ok = self.client.login(email='admin@acme.com', password='pass')
            self.assertTrue(ok)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.client.logout()

            ok = self.client.login(email='staff@acme.com', password='pass')
            self.assertTrue(ok)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.client.logout()

            ok = self.client.login(email='user@acme.com', password='pass')
            self.assertTrue(ok)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

            self.client.logout()

    def testDeviceBatch(self):
        device_template = DeviceTemplate.objects.first()
        sg1 = SensorGraph.objects.create_graph(name='SG 1',
                                               created_by=self.u2, org=self.o1)
        url = reverse('staff:iotile-batch')
        name_format = 'Device {id}'
        payload = {
            'template': device_template.id,
            'sg': sg1.id,
            'org': '',
            'name_format': name_format,
            'num_devices': 10
        }

        self.assertEqual(Device.objects.count(), 0)

        ok = self.client.login(email='staff@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data=payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

        self.assertEqual(Device.objects.count(), 10)
        dev1 = Device.objects.first()
        self.assertEqual(dev1.label, name_format.format(id=int16gid(dev1.id)))
        self.assertIsNone(dev1.org)

        self.client.logout()

    def testUpgradeSgBatch(self):
        device_template = DeviceTemplate.objects.first()
        sg_from = SensorGraph.objects.create_graph(name='SG 1',
                                               created_by=self.u2, org=self.o1)
        sg_to = SensorGraph.objects.create_graph(name='SG 2',
                                               created_by=self.u2, org=self.o1)

        d1= Device.objects.create(label='d1',
                                   sg=sg_from,
                                   template=device_template,
                                  created_by=self.u2)
        d2 = Device.objects.create(label='d2',
                                    sg=sg_from,
                                    template=device_template,
                                   created_by=self.u2)
        d3 = Device.objects.create(label='d3',
                                    sg=sg_from,
                                    template=device_template,
                                   created_by=self.u2)
        d4 = Device.objects.create(label='d4',
                                    sg=sg_to,
                                    template=device_template,
                                   created_by=self.u2)
        self.assertEqual(Device.objects.filter(sg=sg_from).count(), 3)
        self.assertEqual(Device.objects.filter(sg=sg_to).count(), 1)

        url = reverse('staff:upgrade-sg-batch')
        url_confirm = reverse('staff:upgrade-sg-batch-confirm', kwargs={'pk_from': sg_from.pk, 'pk_to': sg_to.pk})

        payload = {'sg_from': sg_from.id,
                   'sg_to': sg_to.id}

        response = self.client.get(url)
        self.assertRedirects(response, '/account/login/?next={0}'.format(url))

        ok = self.client.login(email='user@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.get(url_confirm)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(url_confirm, payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='admin@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url, payload)
        self.assertRedirects(response, url_confirm)

        response = self.client.get(url_confirm)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url_confirm, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(Device.objects.filter(sg=sg_from).count(), 0)
        self.assertEqual(Device.objects.filter(sg=sg_to).count(), 4)

        self.client.logout()

        ok = self.client.login(email='staff@acme.com', password='pass')
        self.assertTrue(ok)

        url_confirm = reverse('staff:upgrade-sg-batch-confirm', kwargs={'pk_from': sg_to.pk, 'pk_to': sg_from.pk})
        payload = {'sg_from': sg_to.id,
                   'sg_to': sg_from.id}

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url, payload)
        self.assertRedirects(response, url_confirm)

        response = self.client.get(url_confirm)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url_confirm, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(Device.objects.filter(sg=sg_from).count(), 4)
        self.assertEqual(Device.objects.filter(sg=sg_to).count(), 0)

        self.client.logout()

    def testDeleteProject(self):
        project = Project.objects.first()
        device_with_properties = Device.objects.create(id=1, project=project, template=self.dt1, created_by=self.u2)
        GenericProperty.objects.create_int_property(slug=device_with_properties.slug,
                                                    created_by=self.u1,
                                                    name='prop1', value=4)
        GenericProperty.objects.create_str_property(slug=device_with_properties.slug,
                                                    created_by=self.u1,
                                                    name='prop2', value='4')
        project_all = Project.objects.all().count()
        device_all = Device.objects.all().count()
        stream_id_all = StreamId.objects.all().count()
        stream_var_all = StreamVariable.objects.all().count()

        url = reverse('staff:project-delete')
        url_confirm = reverse('staff:project-delete-confirm', kwargs={'pk': project.pk})
        payload = {'project': project.id}

        response = self.client.get(url)
        self.assertRedirects(response, '/account/login/?next={0}'.format(url))

        ok = self.client.login(email='user@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.get(url_confirm)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(url_confirm, payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='admin@acme.com', password='pass')
        self.assertTrue(ok)

        stream_id_delete = StreamId.objects.filter(project=project).count()
        stream_var_delete = StreamVariable.objects.filter(project=project).count()
        property_delete = GenericProperty.objects.filter(target=device_with_properties.slug).count()
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url, payload)
        self.assertRedirects(response, url_confirm)

        response = self.client.get(url_confirm)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url_confirm, {})
        self.assertRedirects(response, '/staff/')

        self.assertEqual(Project.objects.all().count(), project_all-1)
        self.assertEqual(Device.objects.all().count(), device_all)
        self.assertEqual(Device.objects.filter(project=project).count(), 0)
        self.assertEqual(StreamVariable.objects.all().count(), stream_var_all - stream_var_delete)
        self.assertEqual(StreamVariable.objects.filter(project=project).count(), 0)
        self.assertEqual(StreamId.objects.all().count(), stream_id_all - stream_id_delete)
        self.assertEqual(StreamId.objects.filter(project=project).count(), 0)
        self.assertEqual(GenericProperty.objects.filter(target=device_with_properties.slug).count(), 0)

        self.client.logout()

        ok = self.client.login(email='staff@acme.com', password='pass')
        self.assertTrue(ok)

        project_all = Project.objects.all().count()
        device_all = Device.objects.all().count()
        stream_id_all = StreamId.objects.all().count()
        stream_var_all = StreamVariable.objects.all().count()
        project = Project.objects.first()

        stream_id_delete = StreamId.objects.filter(project=project).count()
        stream_var_delete = StreamVariable.objects.filter(project=project).count()

        url_confirm = reverse('staff:project-delete-confirm', kwargs={'pk': project.pk})
        payload = {'project': project.id}

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url, payload)
        self.assertRedirects(response, url_confirm)

        response = self.client.get(url_confirm)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url_confirm, {})
        self.assertRedirects(response, '/staff/')

        self.assertEqual(Project.objects.all().count(), project_all - 1)
        self.assertEqual(Device.objects.all().count(), device_all)
        self.assertEqual(Device.objects.filter(project=project).count(), 0)
        self.assertEqual(StreamVariable.objects.all().count(), stream_var_all - stream_var_delete)
        self.assertEqual(StreamVariable.objects.filter(project=project).count(), 0)
        self.assertEqual(StreamId.objects.all().count(), stream_id_all - stream_id_delete)
        self.assertEqual(StreamId.objects.filter(project=project).count(), 0)
        self.assertEqual(GenericProperty.objects.filter(target=device_with_properties.slug).count(), 0)

        self.client.logout()

    def testMoveProject(self):
        project_all = Project.objects.all().count()

        project = Project.objects.first()
        old_org = project.org
        new_org = Org.objects.create(name='My Org', created_by=self.u2)
        self.assertNotEqual(old_org, new_org)

        device_template = DeviceTemplate.objects.first()
        sg_from = SensorGraph.objects.create_graph(name='SG 1',
                                               created_by=self.u2, org=self.o1)
        sg_to = SensorGraph.objects.create_graph(name='SG 2',
                                               created_by=self.u2, org=self.o1)

        d1= Device.objects.create(label='d1',
                                   project=project,
                                   org=old_org,
                                   sg=sg_from,
                                   template=device_template,
                                  created_by=self.u2)
        d2 = Device.objects.create(label='d2',
                                    project=project,
                                    org=old_org,
                                    sg=sg_from,
                                    template=device_template,
                                   created_by=self.u2)
        d3 = Device.objects.create(label='d3',
                                    project=project,
                                    org=old_org,
                                    sg=sg_from,
                                    template=device_template,
                                   created_by=self.u2)
        v1 = StreamVariable.objects.create_variable(
            name='Var A', project=project, lid=1, created_by=self.u2
        )
        v2 = StreamVariable.objects.create_variable(
            name='Var B', project=project, lid=2, created_by=self.u2
        )
        v3 = StreamVariable.objects.create_variable(
            name='Var C', project=project, lid=3, created_by=self.u2
        )
        s1 = StreamId.objects.create_stream(project=project,
                                            device=d1,
                                            variable=v1,
                                            org=old_org,
                                            created_by=self.u2)
        s2 = StreamId.objects.create_stream(project=project,
                                            device=d1,
                                            variable=v2,
                                            org=old_org,
                                            created_by=self.u2)
        s3 = StreamId.objects.create_stream(project=project,
                                            device=d2,
                                            variable=v1,
                                            org=old_org,
                                            created_by=self.u2)
        s4 = StreamId.objects.create_stream(project=project,
                                            device=d2,
                                            variable=v2,
                                            org=old_org,
                                            created_by=self.u2)

        org_all = Org.objects.all().count()
        device_all = Device.objects.all().count()
        stream_id_all = StreamId.objects.all().count()
        stream_var_all = StreamVariable.objects.all().count()

        device_old = Device.objects.filter(project=project.id, org=old_org).count()
        stream_id_old = StreamId.objects.filter(project=project.id, org=old_org).count()
        stream_var_old = StreamVariable.objects.filter(project=project.id, org=old_org).count()

        self.assertEqual(str(project), '{0} - {1}'.format(old_org.name, project.name))
        self.assertEqual(Project.objects.all().count(), project_all)
        self.assertEqual(Device.objects.all().count(), device_all)
        self.assertEqual(Device.objects.filter(project=project, org=old_org).count(), 3)
        self.assertEqual(Device.objects.filter(project=project, org=new_org).count(), 0)
        self.assertEqual(StreamVariable.objects.all().count(), stream_var_all)
        self.assertEqual(StreamVariable.objects.filter(project=project, org=old_org).count(), 3)
        self.assertEqual(StreamVariable.objects.filter(project=project, org=new_org).count(), 0)
        self.assertEqual(StreamId.objects.all().count(), stream_id_all)
        self.assertEqual(StreamId.objects.filter(project=project, org=old_org).count(), 4)
        self.assertEqual(StreamId.objects.filter(project=project, org=new_org).count(), 0)

        url = reverse('staff:project-move')
        url_confirm = reverse('staff:project-move-confirm', kwargs={'pk': project.pk, 'org_slug': new_org.slug})
        payload = {'project': project.id, 'new_org': new_org}

        response = self.client.get(url)
        self.assertRedirects(response, '/account/login/?next={0}'.format(url))

        ok = self.client.login(email='user@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.get(url_confirm)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(url_confirm, payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='admin@acme.com', password='pass')
        self.assertTrue(ok)

        stream_id_move = StreamId.objects.filter(project=project).count()
        stream_id_oldorg = StreamId.objects.filter(org=old_org).count()
        stream_var_move = StreamVariable.objects.filter(project=project).count()
        stream_var_oldorg = StreamVariable.objects.filter(org=old_org).count()
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url, payload)

        response = self.client.get(url_confirm)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url_confirm, {})
        self.assertRedirects(response, '/staff/')

        self.assertEqual(Project.objects.all().count(), project_all)
        self.assertEqual(Device.objects.all().count(), device_all)
        self.assertEqual(Device.objects.filter(project=project, org=old_org).count(), 0)
        self.assertEqual(Device.objects.filter(project=project, org=new_org).count(), 3)
        self.assertEqual(StreamVariable.objects.all().count(), stream_var_all)
        self.assertEqual(StreamVariable.objects.filter(project=project, org=old_org).count(), 0)
        self.assertEqual(StreamVariable.objects.filter(project=project, org=new_org).count(), 3)
        self.assertEqual(StreamId.objects.all().count(), stream_id_all)
        self.assertEqual(StreamId.objects.filter(project=project, org=old_org).count(), 0)
        self.assertEqual(StreamId.objects.filter(project=project, org=new_org).count(), 4)

        self.client.logout()

        ok = self.client.login(email='staff@acme.com', password='pass')
        self.assertTrue(ok)

        project_all = Project.objects.all().count()
        device_all = Device.objects.all().count()
        stream_id_all = StreamId.objects.all().count()
        stream_var_all = StreamVariable.objects.all().count()
        project = Project.objects.first()

        stream_id_delete = StreamId.objects.filter(project=project).count()
        stream_var_delete = StreamVariable.objects.filter(project=project).count()

        url_confirm = reverse('staff:project-move-confirm', kwargs={'pk': project.pk, 'org_slug': new_org.slug})
        payload = {'project': project.id}

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url, payload)

        response = self.client.get(url_confirm)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url_confirm, {})
        self.assertRedirects(response, '/staff/')

        self.assertEqual(Project.objects.all().count(), project_all)
        self.assertEqual(Device.objects.all().count(), device_all)
        self.assertEqual(Device.objects.filter(project=project, org=old_org).count(), 0)
        self.assertEqual(Device.objects.filter(project=project, org=new_org).count(), 3)
        self.assertEqual(StreamVariable.objects.all().count(), stream_var_all)
        self.assertEqual(StreamVariable.objects.filter(project=project, org=old_org).count(), 0)
        self.assertEqual(StreamVariable.objects.filter(project=project, org=new_org).count(), 3)
        self.assertEqual(StreamId.objects.all().count(), stream_id_all)
        self.assertEqual(StreamId.objects.filter(project=project, org=old_org).count(), 0)
        self.assertEqual(StreamId.objects.filter(project=project, org=new_org).count(), 4)

        self.client.logout()

    def testDeviceUnclaim(self):
        project = Project.objects.first()
        d1 = Device.objects.create(id=1, project=project, org=project.org, template=self.dt1, created_by=self.u2)

        v1 = StreamVariable.objects.create_variable(
            name='Var A', project=project, lid=1, created_by=self.u2
        )
        s1 = StreamId.objects.create_stream(project=project,
                                            device=d1,
                                            variable=v1,
                                            created_by=self.u2)
        dt1 = dateutil.parser.parse('2016-09-10T10:00:00Z')
        dt2 = dateutil.parser.parse('2016-09-10T11:00:00Z')

        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt1,
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt2,
            int_value=6
        )

        GenericProperty.objects.create_int_property(slug=d1.slug,
                                                    created_by=self.u2,
                                                    name='prop1', value=4)
        GenericProperty.objects.create_str_property(slug=d1.slug,
                                                    created_by=self.u2,
                                                    name='prop2', value='4')

        self.assertTrue(Device.objects.filter(slug=d1.slug).exists())
        self.assertEqual(Device.objects.filter(slug=d1.slug).first().project, d1.project)
        self.assertEqual(StreamVariable.objects.filter(project=project).count(), 1)
        self.assertEqual(StreamId.objects.filter(device=d1).count(), 1)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 2)
        self.assertEqual(GenericProperty.objects.filter(target=d1.slug).count(), 2)

        url = reverse('staff:device-unclaim-confirm', kwargs={'pk': d1.pk})
        payload = {'clean_streams': False}

        response = self.client.get(url)
        self.assertRedirects(response, '/account/login/?next={0}'.format(url))

        ok = self.client.login(email='user@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='admin@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url, payload)
        self.assertRedirects(response, expected_url='/staff/device/{}/detail/'.format(d1.pk), status_code=302, target_status_code=status.HTTP_200_OK)

        self.client.logout()

    def testDeleteStreamData(self):
        v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=1,
        )
        pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        s1 = StreamId.objects.create_stream(
            project=self.p1, variable=v1, device=pd1, created_by=self.u2
        )

        dt1 = dateutil.parser.parse('2016-09-10T10:00:00Z')
        dt2 = dateutil.parser.parse('2016-09-10T11:00:00Z')
        dt3 = dateutil.parser.parse('2016-09-20T10:00:00Z')
        dt4 = dateutil.parser.parse('2016-09-23T10:00:00Z')
        dt5 = dateutil.parser.parse('2016-09-26T10:00:00Z')
        dt6 = dateutil.parser.parse('2016-09-29T10:00:00Z')

        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt1,
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt2,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt3,
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt4,
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt5,
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt6,
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt6 + datetime.timedelta(seconds=10),
            int_value=8
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt6 + datetime.timedelta(seconds=20),
            int_value=9
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt6 + datetime.timedelta(seconds=30),
            int_value=9
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=dt6 + datetime.timedelta(seconds=40),
            int_value=9
        )

        url_delete = reverse('staff:stream-data-delete', kwargs={'slug': s1.slug})

        # payloads are in local time
        payload_reverse_date = {
            'date_from': '2016-09-10 11:00:00',
            'date_to': '2016-09-10 10:00:00',
            'delete_data': 'Submit'
        }

        # delete dt1,2
        payload_full = {
            'date_from': '2016-09-08 00:00:00',
            'date_to': '2016-09-12 00:00:00',
            'delete_data': 'Submit'
        }

        # delete from dt6
        payload_partial_1 = {
            'date_from': '2016-09-28 10:00:00',
            'date_to': '',
            'delete_data': 'Submit'
        }

        # delete up to dt4
        payload_partial_2 = {
            'date_to': '2016-09-24 10:00:00',
            'date_from': '',
            'delete_data': 'Submit'
        }
        payload_delete_all = {
            'date_from': '',
            'date_to': '',
            'delete_all': 'Delete all stream data and the stream itself'
        }

        payload_no_data = {
            'date_from': '2017-09-10 10:00:00',
            'date_to': '2017-09-11 10:00:00',
            'delete_data': 'Submit'
        }

        #  as the form parse datetime string as an aware datetime
        url_conf_base = reverse('staff:stream-data-delete-confirm', kwargs={'slug':s1.slug})
        url_conf_full = '{0}?from={1}&to={2}'.format(url_conf_base, str_utc(parse_datetime(payload_full['date_from'])), str_utc(parse_datetime(payload_full['date_to'])))
        url_conf_1 = '{0}?from={1}&to={2}'.format(url_conf_base, str_utc(parse_datetime(payload_partial_1['date_from'])), '')
        url_conf_2 = '{0}?from={1}&to={2}'.format(url_conf_base, '', str_utc(parse_datetime(payload_partial_2['date_to'])))
        url_conf_no_data = '{0}?from={1}&to={2}'.format(url_conf_base, str_utc(parse_datetime(payload_no_data['date_from'])), str_utc(parse_datetime(payload_no_data['date_to'])))
        url_conf_all = '{0}?all=True'.format(url_conf_base)

        self.client.login(email='user@acme.com', password='pass')

        resp = self.client.get(url_delete)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.post(url_delete, payload_full)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.get(url_conf_full)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.post(url_conf_full)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        self.client.login(email='staff@acme.com', password='pass')

        resp = self.client.get(url_delete)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.post(url_delete, payload_reverse_date)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFormError(resp, 'form', None, 'The start date must be before the end date')

        resp = self.client.post(url_delete, payload_no_data)
        self.assertRedirects(resp, url_conf_no_data, status_code=302, target_status_code=302)

        # delete dt1,2
        resp = self.client.post(url_delete, payload_full)
        self.assertRedirects(resp, url_conf_full, status_code=302, target_status_code=200)

        resp = self.client.get(url_conf_full)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 10)

        resp = self.client.post(url_conf_full)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 8)

        # delete from dt6
        resp = self.client.post(url_delete, payload_partial_1)
        self.assertRedirects(resp, url_conf_1, status_code=302, target_status_code=200)

        resp = self.client.get(url_conf_1)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 8)

        resp = self.client.post(url_conf_1)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 3)

        # delete up to dt4
        resp = self.client.post(url_delete, payload_partial_2)
        self.assertRedirects(resp, url_conf_2, status_code=302, target_status_code=200)

        resp = self.client.get(url_conf_2)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 3)

        resp = self.client.post(url_conf_2)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 1)

        # delete all, including the streamId
        resp = self.client.post(url_delete, payload_delete_all)
        self.assertRedirects(resp, url_conf_all, status_code=302, target_status_code=200)

        resp = self.client.get(url_conf_all)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 1)

        resp = self.client.post(url_conf_all)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 0)
        self.assertEqual(StreamId.objects.filter(slug=s1.slug).count(), 0)

        self.client.logout()

    def testMoveDeviceStreamData(self):
        project = Project.objects.first()
        org = project.org

        device_template = DeviceTemplate.objects.first()
        sg = SensorGraph.objects.create_graph(name='SG 1', created_by=self.u2, org=self.o1)

        d0= Device.objects.create(label='from',
                                   project=project,
                                   org=org,
                                   sg=sg,
                                   template=device_template,
                                  created_by=self.u2)
        d1 = Device.objects.create(label='to',
                                   project=project,
                                   org=org,
                                   sg=sg,
                                   template=device_template,
                                   created_by=self.u2)
        d2 = Device.objects.create(label='and then',
                                   project=project,
                                   org=org,
                                   sg=sg,
                                   template=device_template,
                                   created_by=self.u2)
        v1 = StreamVariable.objects.create_variable(
            name='Var A', project=project, lid=1, created_by=self.u2
        )
        v2 = StreamVariable.objects.create_variable(
            name='Var B', project=project, lid=2, created_by=self.u2
        )
        s1 = StreamId.objects.create_stream(project=project,
                                            device=d0,
                                            variable=v1,
                                            org=org,
                                            created_by=self.u2)
        s2 = StreamId.objects.create_stream(project=project,
                                            device=d0,
                                            variable=v2,
                                            org=org,
                                            created_by=self.u2)

        t0 = timezone.now() - datetime.timedelta(days=2)
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='ITR',
            timestamp=t0 + datetime.timedelta(seconds=10),
            device_timestamp = 10,
            streamer_local_id=5,
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='ITR',
            timestamp=t0 + datetime.timedelta(seconds=70),
            device_timestamp = 70,
            streamer_local_id=6,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=s2.slug,
            type='ITR',
            timestamp=t0 + datetime.timedelta(days=1),
            device_timestamp = 24*60*60,
            streamer_local_id=7,
            int_value=7
        )
        StreamEventData.objects.create(
            timestamp=t0 + datetime.timedelta(seconds=20),
            device_timestamp = 20,
            stream_slug=s2.slug,
            streamer_local_id=2
        )
        StreamEventData.objects.create(
            timestamp=t0 + datetime.timedelta(days=1),
            device_timestamp = 24*60*60,
            stream_slug=s2.slug,
            streamer_local_id=2
        )


        url = reverse('staff:device-data-move')
        url_confirm = reverse('staff:device-data-move-confirm', kwargs={'dev0': d0.id, 'dev1': d1.id})
        payload = {
            'dev0': d0.id,
            'dev1': d1.id
        }

        response = self.client.get(url)
        self.assertRedirects(response, '/account/login/?next={0}'.format(url))

        ok = self.client.login(email='user@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.get(url_confirm)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(url_confirm, payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='staff@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(StreamVariable.objects.count(), 4)
        self.assertEqual(StreamId.objects.count(), 2)
        self.assertEqual(StreamData.objects.filter(device_slug=d0.slug).count(), 3)
        self.assertEqual(StreamEventData.objects.filter(device_slug=d0.slug).count(), 2)
        self.assertEqual(StreamData.objects.filter(device_slug=d1.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(device_slug=d1.slug).count(), 0)

        response = self.client.post(url, payload)

        response = self.client.get(url_confirm)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url_confirm, {})
        self.assertRedirects(response, '/staff/')

        self.assertEqual(StreamVariable.objects.count(), 4)
        self.assertEqual(StreamId.objects.count(), 4)
        self.assertEqual(StreamData.objects.filter(device_slug=d0.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(device_slug=d0.slug).count(), 0)
        self.assertEqual(StreamData.objects.filter(device_slug=d1.slug).count(), 3)
        self.assertEqual(StreamEventData.objects.filter(device_slug=d1.slug).count(), 2)

        s5 = StreamId.objects.create_stream(project=project,
                                            device=d2,
                                            variable=v1,
                                            org=org,
                                            created_by=self.u2)
        s6 = StreamId.objects.create_stream(project=project,
                                            device=d2,
                                            variable=v2,
                                            org=org,
                                            created_by=self.u2)
        self.assertEqual(StreamVariable.objects.count(), 4)
        self.assertEqual(StreamId.objects.count(), 6)

        url_confirm = reverse('staff:device-data-move-confirm', kwargs={
            'dev0': d1.id,
            'dev1': d2.id
        })+'?start={}'.format(str_utc(t0 + datetime.timedelta(hours=20)))
        response = self.client.post(url_confirm, {})
        self.assertRedirects(response, '/staff/')

        self.assertEqual(StreamVariable.objects.count(), 4)
        self.assertEqual(StreamId.objects.count(), 6)
        self.assertEqual(StreamData.objects.filter(device_slug=d1.slug).count(), 2)
        self.assertEqual(StreamEventData.objects.filter(device_slug=d1.slug).count(), 1)
        self.assertEqual(StreamData.objects.filter(device_slug=d2.slug).count(), 1)
        self.assertEqual(StreamEventData.objects.filter(device_slug=d2.slug).count(), 1)

        self.assertEqual(StreamData.objects.filter(stream_slug=s5.slug).count(), 0)
        self.assertEqual(StreamData.objects.filter(stream_slug=s6.slug).count(), 1)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=s6.slug).count(), 1)

        self.client.logout()

    def testDeviceKeyReset(self):
        project = Project.objects.first()
        d1 = Device.objects.create(id=1, project=project, org=project.org, template=self.dt1, created_by=self.u2)
        d2 = Device.objects.create(id=2, project=project, org=project.org, template=self.dt1, created_by=self.u2)
        d3 = Device.objects.create(id=3, project=project, org=project.org, template=self.dt1, created_by=self.u2)
        DeviceKey.objects.create_device(slug=d2.slug, type='SSH', downloadable=True, secret='abc2', created_by=self.u1)
        DeviceKey.objects.create_device(slug=d3.slug, type='SSH', downloadable=False, secret='abc3', created_by=self.u1)

        self.assertTrue(Device.objects.filter(slug=d1.slug).exists())
        self.assertEqual(DeviceKey.objects.count(), 2)
        self.assertEqual(DeviceKey.objects.filter(slug=d1.slug).count(), 0)

        url = reverse('staff:device-reset-key-confirm', kwargs={'pk': d1.pk})
        payload = {}

        response = self.client.get(url)
        self.assertRedirects(response, '/account/login/?next={0}'.format(url))

        ok = self.client.login(email='user@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='admin@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url, payload)
        self.assertRedirects(response, '/staff/device/1/detail/')

        self.assertTrue(Device.objects.filter(slug=d1.slug).exists())
        self.assertEqual(DeviceKey.objects.filter(slug=d1.slug).count(), 0)
        DeviceKey.objects.create_device(slug=d1.slug, type='SSH', downloadable=True,
                                        secret='abc1', created_by=self.u1)
        self.assertEqual(DeviceKey.objects.filter(slug=d1.slug).count(), 1)

        response = self.client.post(url, payload)
        self.assertRedirects(response, '/staff/device/1/detail/')
        self.assertEqual(DeviceKey.objects.filter(slug=d1.slug).count(), 0)

        self.client.logout()

        ok = self.client.login(email='staff@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(url, payload)
        self.assertRedirects(response, '/staff/device/1/detail/')

        self.assertTrue(Device.objects.filter(slug=d1.slug).exists())
        self.assertEqual(DeviceKey.objects.filter(slug=d1.slug).count(), 0)
        DeviceKey.objects.create_device(slug=d1.slug, type='SSH', downloadable=True,
                                        secret='abc1', created_by=self.u1)
        self.assertEqual(DeviceKey.objects.filter(slug=d1.slug).count(), 1)

        response = self.client.post(url, payload)
        self.assertRedirects(response, '/staff/device/1/detail/')
        self.assertEqual(DeviceKey.objects.filter(slug=d1.slug).count(), 0)
        self.assertEqual(DeviceKey.objects.filter(slug=d2.slug).count(), 1)
        self.assertEqual(DeviceKey.objects.filter(slug=d3.slug).count(), 1)

        self.client.logout()

    def testDeviceKeyDetail(self):
        project = Project.objects.first()
        d1 = Device.objects.create(id=1, project=project, org=project.org, template=self.dt1, created_by=self.u2)
        d2 = Device.objects.create(id=2, project=project, org=project.org, template=self.dt1, created_by=self.u2)

        url = reverse('staff:keys', kwargs={'pk': d1.pk})

        response = self.client.get(url)
        self.assertRedirects(response, '/account/login/?next={0}'.format(url))

        ok = self.client.login(email='admin@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.context['object'], d1)
        self.assertEqual(response.context['key_list'].count(), 0)
        self.assertTemplateUsed(response, 'staff/keys-list.html')

        url = reverse('staff:keys', kwargs={'pk': d2.pk})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.context['object'], d2)
        self.assertEqual(response.context['key_list'].count(), 0)

        k1 = DeviceKey.objects.create_device(
            slug=d1.slug, type='SSH', downloadable=True, secret='ssh-secret', created_by=self.u1
        )
        k2 = DeviceKey.objects.create_device(
            slug=d2.slug, type='SSH', downloadable=True, secret='ssh-secret', created_by=self.u1
        )
        k3 = DeviceKey.objects.create_device(
            slug=d1.slug, type='USR', downloadable=False, secret='usr-secret', created_by=self.u1
        )
        k4 = DeviceKey.objects.create_device(
            slug=d2.slug, type='USR', downloadable=False, secret='usr-secret', created_by=self.u1
        )

        self.assertTrue(Device.objects.filter(slug=d1.slug).exists())
        self.assertEqual(DeviceKey.objects.count(), 4)
        self.assertEqual(DeviceKey.objects.filter(slug=d1.slug).count(), 2)
        self.assertEqual(DeviceKey.objects.filter(slug=d2.slug).count(), 2)

        url = reverse('staff:keys', kwargs={'pk': d1.pk})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.context['object'], d1)
        self.assertEqual(response.context['key_list'].count(), 1)
        self.assertEqual(response.context['key_list'].get(type='SSH'), k1)
        self.assertTemplateUsed(response, 'staff/keys-list.html')

        url = reverse('staff:keys', args=[d2.pk])

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.context['object'], d2)
        self.assertEqual(response.context['key_list'].count(), 1)
        self.assertEqual(response.context['key_list'].get(type='SSH'), k2)
        self.assertTemplateUsed(response, 'staff/keys-list.html')

        self.client.logout()
