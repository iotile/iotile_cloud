from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from rest_framework import status

from apps.utils.utest.devices import TripDeviceMock
from apps.sqsworker.exceptions import WorkerActionHardError
from apps.utils.test_util import TestMixin
from apps.org.models import Org
from apps.project.models import Project
from apps.physicaldevice.models import Device
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.streamnote.models import StreamNote
from apps.devicelocation.models import DeviceLocation
from apps.property.models import GenericProperty
from apps.report.models import GeneratedUserReport

from ..worker.device_move import DeviceMoveAction

user_model = get_user_model()


class DeviceMoveTests(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()

        self.device_mock = TripDeviceMock()

        self.o2 = Org.objects.get(slug='user-org')
        self.o2.register_user(self.u2, role='a1')

        self.p1 = Project.objects.get(name='Project 1')
        self.device1 = self.p1.devices.first()

    def tearDown(self):
        self.device_mock.tearDown()
        self.userTestTearDown()
        StreamNote.objects.all().delete()
        StreamEventData.objects.all().delete()

    def testDeviceMoveActionBadArguments(self):
        with self.assertRaises(WorkerActionHardError):
            DeviceMoveAction.schedule(args={})
        with self.assertRaises(WorkerActionHardError):
            DeviceMoveAction.schedule(args={'foobar': 5})
        with self.assertRaises(WorkerActionHardError):
            DeviceMoveAction.schedule(args={
                'device_slug': 'd--0000-0000-0000-0001',
                'project_slug': 'p--0000-0001',
                'extra-bad-arg': 'foo'
            })

        self.assertTrue(DeviceMoveAction._arguments_ok({
            'device_slug': 'd--0000-0000-0000-0001',
            'project_slug': 'p--0000-0001',
            'user': 'slug'
        }))

        action = DeviceMoveAction()
        self.assertIsNotNone(action)
        with self.assertRaises(WorkerActionHardError):
            action.execute(arguments={'foobar': 5})

    def testDeviceMoveActionTestAll(self):

        device = self.device1
        s1_slug = str(device.get_stream_slug_for('5020'))
        s2_slug = str(device.get_stream_slug_for('5023'))

        new_project = Project.objects.create(name='new', org=device.org, created_by=self.u2)

        StreamNote.objects.create(
            target_slug=s1_slug,
            timestamp=timezone.now(),
            created_by=self.u2,
            note='Note 1'
        )
        StreamNote.objects.create(
            target_slug=s1_slug,
            timestamp=timezone.now(),
            created_by=self.u2,
            note='Note 2'
        )
        StreamNote.objects.create(
            target_slug=s1_slug,
            timestamp=timezone.now(),
            created_by=self.u2,
            note='Note 3'
        )
        StreamNote.objects.create(
            target_slug=device.slug,
            timestamp=timezone.now(),
            created_by=self.u1,
            note='Note 4'
        )
        DeviceLocation.objects.create(
            timestamp=timezone.now(),
            target_slug=device.slug,
            lat=12.1234, lon=10.000,
            user=self.u2
        )

        GeneratedUserReport.objects.create(
            org=device.org,
            label='My report 1',
            source_ref=device.slug,
            created_by=self.u2
        )

        self.assertEqual(GenericProperty.objects.object_properties_qs(device).count(), 4)

        self.assertEqual(device.streamids.count(), 9)
        self.assertEqual(device.project.variables.filter(project=device.project).count(), 10)

        self.assertEqual(StreamData.objects.filter(stream_slug=s1_slug).count(), 0)
        self.assertEqual(StreamData.objects.filter(stream_slug=s2_slug).count(), 5)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=s1_slug).count(), 10)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=s2_slug).count(), 0)
        self.assertEqual(StreamNote.objects.filter(target_slug=s1_slug).count(), 3)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 1)
        self.assertEqual(DeviceLocation.objects.filter(target_slug=device.slug).count(), 1)
        self.assertEqual(GeneratedUserReport.objects.filter(source_ref=device.slug).count(), 1)

        action = DeviceMoveAction()
        action.execute(arguments={
            'device_slug': device.slug,
            'project_slug': new_project.slug,
            'move_data': True,
            'user': self.u2.slug
        })

        self.assertEqual(self.p1.devices.count(), 0)
        self.assertEqual(device.streamids.filter(project=self.p1).count(), 0)
        self.assertEqual(new_project.devices.count(), 1)
        device = new_project.devices.first()

        self.assertEqual(GenericProperty.objects.object_properties_qs(device).count(), 4)

        self.assertEqual(device.streamids.count(), 9)
        self.assertEqual(device.streamids.filter(project=new_project).count(), 9)
        self.assertEqual(new_project.variables.filter(project=new_project).count(), 9)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1_slug).count(), 0)
        self.assertEqual(StreamData.objects.filter(stream_slug=s2_slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=s1_slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=s2_slug).count(), 0)
        self.assertEqual(StreamNote.objects.filter(target_slug=s1_slug).count(), 0)
        self.assertEqual(StreamNote.objects.filter(target_slug=device.slug).count(), 2)
        self.assertEqual(DeviceLocation.objects.filter(target_slug=device.slug).count(), 1)
        self.assertEqual(GeneratedUserReport.objects.filter(source_ref=device.slug).count(), 1)
        system_note = StreamNote.objects.filter(target_slug=device.slug).last()
        self.assertTrue('Device was moved' in system_note.note)

        new_s1_slug = str(device.get_stream_slug_for('5020'))
        new_s2_slug = str(device.get_stream_slug_for('5023'))
        self.assertEqual(StreamData.objects.filter(stream_slug=new_s1_slug).count(), 0)
        self.assertEqual(StreamData.objects.filter(stream_slug=new_s2_slug).count(), 5)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=new_s1_slug).count(), 10)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=new_s2_slug).count(), 0)
        self.assertEqual(StreamNote.objects.filter(target_slug=new_s1_slug).count(), 3)

    def testDeviceMoveActionMoveDataFalseTestAll(self):

        device = self.device1
        s1_slug = str(device.get_stream_slug_for('5020'))
        s2_slug = str(device.get_stream_slug_for('5023'))

        new_project = Project.objects.create(name='new', org=device.org, created_by=self.u2)

        self.assertEqual(device.streamids.count(), 9)
        self.assertEqual(device.project.variables.filter(project=device.project).count(), 10)

        self.assertEqual(StreamData.objects.filter(stream_slug=s1_slug).count(), 0)
        self.assertEqual(StreamData.objects.filter(stream_slug=s2_slug).count(), 5)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=s1_slug).count(), 10)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=s2_slug).count(), 0)

        action = DeviceMoveAction()
        action.execute(arguments={
            'device_slug': device.slug,
            'project_slug': new_project.slug,
            'move_data': False,
            'user': self.u2.slug
        })

        self.assertEqual(self.p1.devices.count(), 0)
        self.assertEqual(device.streamids.filter(project=self.p1).count(), 9)
        self.assertEqual(new_project.devices.count(), 1)
        device = new_project.devices.first()

        self.assertEqual(device.streamids.count(), 18)
        self.assertEqual(device.streamids.filter(project=new_project).count(), 9)
        self.assertEqual(new_project.streamids.filter(project=new_project).count(), 9)
        self.assertEqual(new_project.variables.filter(project=new_project).count(), 9)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1_slug).count(), 0)
        self.assertEqual(StreamData.objects.filter(stream_slug=s2_slug).count(), 5)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=s1_slug).count(), 10)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=s2_slug).count(), 0)

        new_s1_slug = str(device.get_stream_slug_for('5020'))
        new_s2_slug = str(device.get_stream_slug_for('5023'))
        self.assertEqual(StreamData.objects.filter(stream_slug=new_s1_slug).count(), 0)
        self.assertEqual(StreamData.objects.filter(stream_slug=new_s2_slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=new_s1_slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=new_s2_slug).count(), 0)

    def testDeviceMoveView(self):
        device = Device.objects.create(
            label="d11", project=self.p1, org=self.p1.org,
            template=self.device1.template, created_by=self.u2
        )
        project = Project.objects.create(
            name='Project 20', project_template=self.p1.project_template,
            created_by=self.u2, org=self.p1.org
        )
        v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=1,
        )
        v2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p1, created_by=self.u3, lid=2,
        )
        s1 = StreamId.objects.create_stream(
            project=self.p1, variable=v1, device=device, created_by=self.u2
        )
        s2 = StreamId.objects.create_stream(
            project=self.p1, variable=v2, device=device, created_by=self.u2
        )

        self.assertEqual(s1.device, device)
        self.assertEqual(s2.device, device)
        self.assertEqual(v1.project, self.p1)
        self.assertEqual(v2.project, self.p1)
        self.assertEqual(self.p1.variables.count(), 12)
        self.assertEqual(v1.streamids.count(), 1)
        self.assertEqual(v2.streamids.count(), 1)
        self.assertEqual(self.p1.devices.count(), 2)
        self.assertEqual(device.streamids.count(), 2)
        self.assertEqual(self.p1.streamids.count(), 11)

        #move to new project
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        url = reverse('org:project:device:move', kwargs={
            'org_slug':device.org.slug, 'project_id': device.project.id, 'pk': device.id
        })
        self.assertEqual(project.devices.count(), 0)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'Move IOTile Device')

        self.assertEqual(self.p1.org, project.org)
        data = {'dst_project': project.id, 'move_data': True}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

        url = reverse('org:project:device:detail', kwargs={
            'org_slug':project.org.slug, 'project_id': project.id, 'pk': device.id
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, project.name)
        self.assertContains(response, device.slug)

        project = Project.objects.get(id=project.id)
        device = Device.objects.get(id=device.id)
        self.assertEqual(s1.device, device)
        self.assertEqual(s2.device, device)
        self.assertEqual(v1.project, self.p1)
        self.assertEqual(v2.project, self.p1)
        self.assertEqual(self.p1.variables.count(), 12)
        # Variables are only created from SG. Not important here
        self.assertEqual(project.variables.count(), 0)
        # But the streams will be moved anyway
        self.assertEqual(device.streamids.count(), 2)
        self.assertEqual(project.streamids.count(), 2)

        self.client.logout()
