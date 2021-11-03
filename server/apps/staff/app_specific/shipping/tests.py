import datetime
import time
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.contrib.messages import get_messages

from rest_framework import status

from apps.utils.test_util import TestMixin
from apps.stream.models import StreamId
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.physicaldevice.models import Device
from apps.devicetemplate.models import DeviceTemplate
from apps.configattribute.models import ConfigAttribute
from apps.projecttemplate.models import ProjectTemplate
from apps.sensorgraph.models import SensorGraph
from apps.project.models import Project
from apps.org.models import Org
from apps.utils.iotile.variable import SYSTEM_VID
from apps.streamfilter.models import StreamFilter, StreamFilterTrigger, State, StreamFilterAction, StateTransition

user_model = get_user_model()

class StaffShippingTestCase(TestMixin, TestCase):

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
        StreamFilterAction.objects.all().delete()
        StreamFilterTrigger.objects.all().delete()
        State.objects.all().defer()
        StreamFilter.objects.all().delete()
        StreamId.objects.all().delete()
        Device.objects.all().delete()
        ConfigAttribute.objects.all().delete()
        SensorGraph.objects.all().delete()
        ProjectTemplate.objects.all().delete()
        DeviceTemplate.objects.all().delete()
        StreamData.objects.all().delete()
        StreamEventData.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testAccessControls(self):

        url_list = [
            reverse('staff:shipping'),
            reverse('staff:shipping-org'),
            reverse('staff:shipping-project'),
            reverse('staff:shipping-claim'),
            reverse('staff:shipping-data-fix'),
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

    def testNewOrg(self):
        url = reverse('staff:shipping-org')
        payload = {
            'name': 'Acme Corp',
            'short_name': 'acme',
            'owner': 'new',
        }

        self.assertEqual(ConfigAttribute.objects.count(), 0)
        self.assertEqual(user_model.objects.count(), 6)
        self.assertEqual(Org.objects.count(), 3)

        ok = self.client.login(email='staff@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data=payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

        self.assertEqual(user_model.objects.count(), 7)
        self.assertEqual(Org.objects.count(), 4)

        user = user_model.objects.get(slug='support-acme')
        self.assertEqual(user.username, 'support-acme')
        self.assertEqual(user.name, 'Arch Support')
        self.assertEqual(user.email, 'help+acme@archsys.io')

        org = Org.objects.get(slug='acme-corp')
        self.assertEqual(org.created_by, user)
        self.assertTrue(org.is_member(user))
        self.assertTrue(org.is_admin(user))

        # Now check that ConfigAttributes were also added
        self.assertEqual(ConfigAttribute.objects.count(), 5)


        self.client.logout()

    def testNewProject(self):
        org = Org.objects.create(name='My Shipping Org', created_by=self.u2)
        url = reverse('staff:shipping-project')
        payload = {
            'name': 'Shipping Project 1',
            'org': org.id,
        }

        self.assertEqual(Project.objects.count(), 4)
        self.assertEqual(org.projects.count(), 0)

        ok = self.client.login(email='staff@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data=payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

        self.client.logout()

        self.assertEqual(Project.objects.count(), 5)
        self.assertEqual(org.projects.count(), 1)

        project = Project.objects.get(name='Shipping Project 1')
        self.assertEqual(project.org, org)
        self.assertEqual(project.created_by, self.u2)

        # Check filters
        self.assertEqual(StreamFilter.objects.count(), 3)
        self.assertEqual(State.objects.count(), 3)
        self.assertEqual(StreamFilterAction.objects.count(), 3)
        self.assertEqual(StateTransition.objects.count(), 3)
        self.assertEqual(StreamFilterTrigger.objects.count(), 3)

        for state in State.objects.all():
            self.assertTrue(state.label in ['END', 'UPDATE', 'DATA_UPDATE'])

        for trigger in StreamFilterTrigger.objects.all():
            self.assertEqual(trigger.operator, 'bu')

        f1 = StreamFilter.objects.get(name='End of Trip')
        self.assertTrue(f1.active)
        self.assertEqual(f1.project, project)
        self.assertEqual(f1.variable.lid, 0x0e01)

        f2 = StreamFilter.objects.get(name='Trip Update')
        self.assertTrue(f2.active)
        self.assertEqual(f2.project, project)
        self.assertEqual(f2.variable.lid, 0x5a08)

        f3 = StreamFilter.objects.get(name='Mid-Trip Data Upload')
        self.assertTrue(f3.active)
        self.assertEqual(f3.project, project)
        self.assertEqual(f3.variable.lid, 0x5a0c)

        a1 = StreamFilterAction.objects.get(state=State.objects.get(label='END'))
        self.assertEqual(a1.on, 'entry')
        self.assertEqual(a1.type, 'smry')
        self.assertTrue('generator' in a1.extra_payload)
        self.assertTrue('notification_recipients' in a1.extra_payload)
        self.assertEqual(a1.extra_payload['generator'], 'end_of_trip')
        self.assertEqual(a1.extra_payload['notification_recipients'], ['org:admin'])

        a2 = StreamFilterAction.objects.get(state=State.objects.get(label='UPDATE'))
        self.assertEqual(a2.on, 'entry')
        self.assertEqual(a2.type, 'smry')
        self.assertTrue('generator' in a2.extra_payload)
        self.assertTrue('notification_recipients' in a2.extra_payload)
        self.assertEqual(a2.extra_payload['generator'], 'trip_update')
        self.assertEqual(a2.extra_payload['notification_recipients'], ['org:admin'])

        a3 = StreamFilterAction.objects.get(state=State.objects.get(label='DATA_UPDATE'))
        self.assertEqual(a3.on, 'entry')
        self.assertEqual(a3.type, 'smry')
        self.assertTrue('generator' in a3.extra_payload)
        self.assertTrue('notification_recipients' in a3.extra_payload)
        self.assertEqual(a3.extra_payload['generator'], 'end_of_trip')
        self.assertEqual(a3.extra_payload['notification_recipients'], ['org:admin'])

    def testDeviceClaim(self):
        dt = DeviceTemplate.objects.create(external_sku='POD-1M [ae1]',
                                           major_version=1, released_on=timezone.now(),
                                           created_by=self.u2, org=self.o2)
        pt = ProjectTemplate.objects.create(name='Shipping Template',
                                            major_version=1,
                                            created_by=self.u2, org=self.o2)
        org = Org.objects.create(name='My Shipping Org', created_by=self.u2)
        project = Project.objects.create(name='Shipping Project 1', created_by=self.u2, org=org, project_template=pt)
        device = Device.objects.create(id=100, template=dt, created_by=self.u2)

        url = reverse('staff:shipping-claim')
        payload = {
            'device_id': device.id,
            'project': project.id,
        }

        ok = self.client.login(email='staff@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data=payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

        messages = [msg.message for msg in get_messages(response.wsgi_request)]
        self.assertEqual('Device has no Sensor Graph', str(messages[0]))

        sg = SensorGraph.objects.create(name='Shipping', major_version=1,
                                        created_by=self.u2, org=self.o1)
        device.sg = sg
        device.save()

        response = self.client.post(url, data=payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

        device = Device.objects.get(id=100)
        self.assertEqual(device.state, 'N0')

        self.client.logout()

    def testDeviceDataFix(self):
        template = DeviceTemplate.objects.create(
            external_sku='POD-1M [ae1]', major_version=1, released_on=timezone.now(),
            created_by=self.u2, org=self.o1
        )
        ptemplate = ProjectTemplate.objects.create(
            name='Shipping Template', major_version=1, created_by=self.u2, org=self.o1
        )
        sensor_graph = SensorGraph.objects.create(
            name='Shipping', major_version=1, created_by=self.u2, org=self.o1
        )
        org = Org.objects.create(name='My Shipping Org', created_by=self.u2)
        project = Project.objects.create(
            name='P1', created_by=self.u2, org=org, project_template=ptemplate
        )
        device = Device.objects.create(
            id=100, template=template, sg=sensor_graph, created_by=self.u2,
            org=org, project=project
        )

        ts_now1 = timezone.now() - datetime.timedelta(seconds=1000)
        epoch_time = int(time.time()) - 1000
        trip_start_stream_slug = str(device.get_stream_slug_for(SYSTEM_VID['TRIP_START']))
        trip_end_stream_slug = str(device.get_stream_slug_for(SYSTEM_VID['TRIP_END']))
        trip_shock_stream_slug = str(device.get_stream_slug_for('5020'))
        trip_env_stream_slug = str(device.get_stream_slug_for('5021'))
        StreamData.objects.create(
            stream_slug=trip_start_stream_slug,
            type='Num',
            timestamp=ts_now1,
            device_timestamp=100,
            streamer_local_id=10,
            int_value=epoch_time+100
        )
        StreamData.objects.create(
            stream_slug=trip_env_stream_slug,
            type='Num',
            timestamp=ts_now1 + datetime.timedelta(seconds=10000),
            device_timestamp=200,
            streamer_local_id=11,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=trip_env_stream_slug,
            type='Num',
            timestamp=ts_now1 + datetime.timedelta(seconds=20000),
            device_timestamp=300,
            streamer_local_id=12,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=trip_shock_stream_slug,
            type='Num',
            timestamp=ts_now1 + datetime.timedelta(seconds=21000),
            device_timestamp=340,
            streamer_local_id=13,
            int_value=130
        )
        StreamData.objects.create(
            stream_slug=trip_shock_stream_slug,
            type='Num',
            timestamp=ts_now1 + datetime.timedelta(seconds=22000),
            device_timestamp=350,
            streamer_local_id=14,
            int_value=131
        )
        StreamData.objects.create(
            stream_slug=trip_shock_stream_slug,
            type='Num',
            timestamp=ts_now1 + datetime.timedelta(seconds=23000),
            device_timestamp=360,
            streamer_local_id=15,
            int_value=132
        )
        StreamEventData.objects.create(
            timestamp=ts_now1 + datetime.timedelta(seconds=50000),
            device_timestamp=340,
            stream_slug=trip_shock_stream_slug,
            streamer_local_id=130
        )
        StreamEventData.objects.create(
            timestamp=ts_now1 + datetime.timedelta(seconds=54000),
            device_timestamp=350,
            stream_slug=trip_shock_stream_slug,
            streamer_local_id=131
        )
        StreamEventData.objects.create(
            timestamp=ts_now1 + datetime.timedelta(seconds=56000),
            device_timestamp=360,
            stream_slug=trip_shock_stream_slug,
            streamer_local_id=132
        )
        StreamData.objects.create(
            stream_slug=trip_end_stream_slug,
            type='Num',
            timestamp=ts_now1 + datetime.timedelta(seconds=300),
            device_timestamp=400,
            streamer_local_id=20,
            int_value=epoch_time+400
        )
        url = reverse('staff:shipping-data-fix')
        payload = {
            'device_id': device.id
        }

        ok = self.client.login(email='staff@acme.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, data=payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

        for data in StreamData.objects.filter(stream_slug=trip_env_stream_slug):
            self.assertTrue(data.timestamp > ts_now1 + datetime.timedelta(seconds=100))
            self.assertTrue(data.timestamp < ts_now1 + datetime.timedelta(seconds=400))
        for event in StreamEventData.objects.filter(stream_slug=trip_shock_stream_slug):
            self.assertTrue(event.timestamp > ts_now1 + datetime.timedelta(seconds=100))
            self.assertTrue(event.timestamp < ts_now1 + datetime.timedelta(seconds=400))

        self.client.logout()
