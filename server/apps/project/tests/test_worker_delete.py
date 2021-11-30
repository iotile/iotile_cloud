import datetime

from django.core import mail
from django.test import TestCase
from django.utils.dateparse import parse_datetime

from apps.org.models import OrgMembership
from apps.physicaldevice.models import Device
from apps.sqsworker.exceptions import WorkerActionHardError
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.streamfilter.models import *
from apps.streamnote.models import StreamNote
from apps.utils.test_util import TestMixin

from ..worker.delete_project import ProjectDeleteAction


class ProjectDeleteTests(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=1,
        )
        self.v2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p1, created_by=self.u3, lid=2,
        )
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p1, label='d2', template=self.dt1, created_by=self.u2)
        StreamId.objects.create_after_new_device(self.pd1)
        StreamId.objects.create_after_new_device(self.pd2)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()
        self.s2 = StreamId.objects.filter(variable=self.v2).first()

    def tearDown(self):
        StreamFilterAction.objects.all().delete()
        StreamFilterTrigger.objects.all().delete()
        StreamFilter.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        StreamNote.objects.all().delete()
        Device.objects.all().delete()
        StreamData.objects.all().delete()
        StreamEventData.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testProjectDeleteActionBadArguments(self):
        with self.assertRaises(WorkerActionHardError):
            ProjectDeleteAction.schedule(args={})
        with self.assertRaises(WorkerActionHardError):
            ProjectDeleteAction.schedule(args={'foobar': 5})
        with self.assertRaises(WorkerActionHardError):
            ProjectDeleteAction.schedule(args={
                'project_slug': 'p--0000-0001', 'user': self.u1.slug, 'extra-bad-arg': 'foo',
            })

        self.assertTrue(ProjectDeleteAction._arguments_ok({
            'project_slug': 'p--0000-0001', 'user': self.u1.slug,
        }))

        action = ProjectDeleteAction()
        self.assertIsNotNone(action)
        with self.assertRaises(WorkerActionHardError):
            action.execute(arguments={'foobar': 5})

    def testProjectDeleteActionNonExistingProject(self):

        action = ProjectDeleteAction()
        self.assertIsNotNone(action)
        with self.assertRaises(WorkerActionHardError):
            action.execute({
                'device_slug': 'p--4242-4242', 'user': self.u1.slug,
            })

    def testProjectDeleteActionTestAll(self):

        OrgMembership(user=self.u2, org=self.o3).save()

        device = Device.objects.create_device(project=self.p2, label='d3', template=self.dt1, created_by=self.u2)
        stream1 = StreamId.objects.create_stream(
            project=self.p2, variable=self.v1, device=device, created_by=self.u2,
        )
        stream2 = StreamId.objects.create_stream(
            project=self.p2, variable=self.v2, device=device, created_by=self.u2,
        )
        variable1 = StreamVariable.objects.create_variable(
            name='Var 2A', project=self.p2, created_by=self.u3, lid=3,
        )
        variable2 = StreamVariable.objects.create_variable(
            name='Var 2B', project=self.p2, created_by=self.u3, lid=4,
        )

        ts_now0 = parse_datetime('2018-01-02T23:31:36Z')

        note1 = StreamNote.objects.create(
            target_slug=self.p2.slug, timestamp=ts_now0, note='msg', created_by=self.u2,
        )

        note2 = StreamNote.objects.create(
            target_slug=self.p2.slug, timestamp=ts_now0, note='system msg', created_by=self.u2, type='sc'
        )

        for i in [10, 100, 150, 200, 270]:
            StreamData.objects.create(
                timestamp=ts_now0 + datetime.timedelta(seconds=i),
                device_timestamp=i,
                stream_slug=stream1.slug,
                type='ITR',
                streamer_local_id=i,
                value=i,
            )
        for i in [11, 101, 151, 201]:
            StreamData.objects.create(
                timestamp=ts_now0 + datetime.timedelta(seconds=i),
                device_timestamp=i,
                stream_slug=stream2.slug,
                type='ITR',
                streamer_local_id=i,
                value=i,
            )
            StreamEventData.objects.create(
                timestamp=ts_now0 + datetime.timedelta(seconds=i),
                device_timestamp=i,
                stream_slug=stream2.slug,
                streamer_local_id=i,
                extra_data={'value': i},
            )
        
        self.assertEqual(StreamVariable.objects.all().count(), 6)
        self.assertEqual(StreamId.objects.all().count(), 6)
        self.assertEqual(StreamData.objects.all().count(), 9)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamNote.objects.all().count(), 2)

        self.assertEqual(StreamVariable.objects.filter(project=self.p2).count(), 2)
        self.assertEqual(StreamId.objects.filter(project=self.p2).count(), 2)
        self.assertEqual(StreamData.objects.filter(project_slug=self.p2.slug).count(), 9)
        self.assertEqual(StreamEventData.objects.filter(project_slug=self.p2.slug).count(), 4)
        self.assertEqual(StreamNote.objects.filter(target_slug=self.p2.slug).count(), 2)


        self.assertEqual(len(mail.outbox), 0)

        # Failure because there is a device still claimed by the project
        action = ProjectDeleteAction()
        action.execute(arguments={
            'project_slug': self.p2.slug,
            'user': self.u2.slug,
        })

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'IOTile Cloud Notification')
        self.assertEqual(set(mail.outbox[0].recipients()), set(['user2@foo.com']))

        self.assertEqual(StreamVariable.objects.all().count(), 6)
        self.assertEqual(StreamId.objects.all().count(), 6)
        self.assertEqual(StreamData.objects.all().count(), 9)
        self.assertEqual(StreamEventData.objects.all().count(), 4)
        self.assertEqual(StreamNote.objects.all().count(), 2)

        self.assertEqual(StreamVariable.objects.filter(project=self.p2).count(), 2)
        self.assertEqual(StreamId.objects.filter(project=self.p2).count(), 2)
        self.assertEqual(StreamData.objects.filter(project_slug=self.p2.slug).count(), 9)
        self.assertEqual(StreamEventData.objects.filter(project_slug=self.p2.slug).count(), 4)
        self.assertEqual(StreamNote.objects.filter(target_slug=self.p2.slug).count(), 2)

        device.delete()
        # Success when there is no device claimed by the project
        action = ProjectDeleteAction()
        action.execute(arguments={
            'project_slug': self.p2.slug,
            'user': self.u2.slug,
        })

        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[1].subject, 'IOTile Cloud Notification')
        self.assertEqual(set(mail.outbox[1].recipients()), set(['user2@foo.com', 'user3@foo.com']))

        self.assertEqual(StreamVariable.objects.all().count(), 4)
        self.assertEqual(StreamId.objects.all().count(), 4)
        self.assertEqual(StreamData.objects.all().count(), 0)
        self.assertEqual(StreamEventData.objects.all().count(), 0)
        self.assertEqual(StreamNote.objects.all().count(), 1)

        self.assertEqual(StreamVariable.objects.filter(project=self.p2).count(), 0)
        self.assertEqual(StreamId.objects.filter(project=self.p2).count(), 0)
        self.assertEqual(StreamData.objects.filter(project_slug=self.p2.slug).count(), 0)
        self.assertEqual(StreamEventData.objects.filter(project_slug=self.p2.slug).count(), 0)
        self.assertEqual(StreamNote.objects.filter(target_slug=self.p2.slug).count(), 1)
