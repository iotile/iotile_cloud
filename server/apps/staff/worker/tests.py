import dateutil.parser

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.dateparse import parse_datetime

from rest_framework import status

from iotile_cloud.utils.gid import IOTileStreamSlug, IOTileVariableSlug

from apps.datablock.models import DataBlock
from apps.datablock.worker.archive_device_data import ArchiveDeviceDataAction
from apps.devicetemplate.models import DeviceTemplate
from apps.org.models import Org
from apps.physicaldevice.claim_utils import device_claim
from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.property.models import GenericProperty
from apps.sqsworker.tests import QueueTestMock
from apps.sqsworker.workerhelper import Worker
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.utils.test_util import TestMixin
from apps.utils.utest.devices import ThreeWaterMetersDeviceMocks
from apps.vartype.models import VarType

user_model = get_user_model()

class RemoveDuplicateTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.device_mocks = ThreeWaterMetersDeviceMocks()
        self.o2 = Org.objects.get(name='User Org')
        self.p1 = Project.objects.get(name='Project 1')
        self.p2 = Project.objects.get(name='Project 2')
        self.pd1 = self.p1.devices.first()
        self.pd2 = self.p2.devices.first()
        self.s1 = self.pd1.streamids.first()
        self.s2 = self.pd2.streamids.first()

    def tearDown(self):
        self.device_mocks.tearDown()
        StreamData.objects.all().delete()
        StreamEventData.objects.all().delete()
        self.userTestTearDown()

    def testRemoveDuplicate(self):
        t0 = parse_datetime('2017-01-10T10:00:00+00:00')
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            timestamp=t0,
            streamer_local_id=1,
            int_value=1
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            timestamp=t0,
            streamer_local_id=1,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            timestamp=t0,
            streamer_local_id=2,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            timestamp=t0,
            streamer_local_id=3,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            timestamp=t0,
            streamer_local_id=3,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            timestamp=t0,
            streamer_local_id=3,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=self.s2.slug,
            timestamp=t0,
            streamer_local_id=3,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=self.s2.slug,
            timestamp=t0,
            streamer_local_id=3,
            int_value=6
        )
        self.assertEqual(StreamData.objects.all().count(), 17)

        queue = QueueTestMock()
        worker = Worker(queue, 2)

        queue.add_messages([
            {
                "module": "apps.staff.worker.remove_duplicate",
                "class": "RemoveDuplicateAction",
                "arguments": {
                    "stream_slug": self.s1.slug,
                }
            }
        ])

        worker.run_once_without_delete()

        self.assertEqual(StreamData.objects.all().count(), 12)
        self.assertEqual(StreamData.objects.filter(stream_slug=self.s1.slug, streamer_local_id=1).count(), 1)

        queue.delete_all()
        queue.add_messages([
            {
                "module": "apps.staff.worker.remove_duplicate",
                "class": "RemoveDuplicateAction",
                "arguments": {
                    "device_slug": self.pd2.slug,
                }
            }
        ])
        worker.run_once_without_delete()

        self.assertEqual(StreamData.objects.all().count(), 11)
        self.assertEqual(StreamData.objects.filter(stream_slug=self.s2.slug, streamer_local_id=3).count(), 1)

    def testSyncUpStreamVariableType(self):

        self.assertEqual(VarType.objects.count(), 1)
        self.assertEqual(self.p1.variables.count(), 2)
        self.assertEqual(StreamId.objects.count(), 6)

        var = self.p1.variables.first()
        var.var_type.stream_data_type = 'E0'
        var.var_type.save()

        queue = QueueTestMock()
        worker = Worker(queue, 2)

        queue.add_messages([
            {
                "module": "apps.staff.worker.staff_operations",
                "class": "StaffOperationsAction",
                "arguments": {
                    "operation": "sync_up_stream_variable_type",
                    "user": self.u1.slug,
                    "args": {
                        "variable": var.slug
                    }
                }
            }
        ])

        worker.run_once_without_delete()

        for stream in var.streamids.all():
            self.assertEqual(stream.data_type, 'E0')
        for stream in self.p2.streamids.all():
            self.assertEqual(stream.data_type, 'D0')


class RemoveProjectsFromArchiveDataBlockTestCase(TestCase, TestMixin):
    databases = '__all__'

    def setUp(self):
        self.usersTestSetup()
        self.device_mocks = ThreeWaterMetersDeviceMocks()
        self.o2 = Org.objects.get(name='User Org')
        self.p1 = Project.objects.get(name='Project 1')
        self.pd1 = self.p1.devices.first()

    def tearDown(self):
        self.device_mocks.tearDown()
        StreamData.objects.all().delete()
        StreamEventData.objects.all().delete()
        self.userTestTearDown()

    def testRemoveProjectFromArchiveDataBlock(self):

        t0 = parse_datetime('2017-01-10T10:00:00+00:00')
        db1 = DataBlock.objects.create(org=self.o2, title='test', device=self.pd1, block=1, created_by=self.u1)

        # 1. Archive data from device pd1 into DataBlock db1
        archive_action = ArchiveDeviceDataAction()
        archive_action._block = db1
        archive_action._device = self.pd1
        archive_action.execute(arguments={'data_block_slug': db1.slug})

        # 2. Manually set streams to refer a project, ensure work is done
        for stream in db1.streamids.all():
            assert stream.block == db1
            # stream.project = self.pd1.project
            new_slug = IOTileStreamSlug()
            new_slug.from_parts(
                self.pd1.project.formatted_gid,
                db1.formatted_gid,
                IOTileVariableSlug(stream.var_lid)
            )
            stream.slug = str(new_slug)
            stream.save()
            # self.assertIsNotNone(stream.project)
            self.assertEqual(stream.slug,
                             's--{0}--{1}--{2}'.format(
                                 self.pd1.project.formatted_gid,
                                 db1.formatted_gid,
                                 IOTileVariableSlug(stream.var_lid).formatted_local_id()
                             ))

            StreamEventData.objects.create(
                timestamp=t0,
                device_timestamp=10,
                stream_slug=stream.slug,
                streamer_local_id=2
            )

            self.assertEqual(StreamEventData.objects.filter(stream_slug=stream.slug).count(), 1)

        # 3. Execute worker to set the stream projects to 0
        queue = QueueTestMock()
        worker = Worker(queue, 2)

        queue.add_messages([
            {
                "module": "apps.staff.worker.staff_operations",
                "class": "StaffOperationsAction",
                "arguments": {
                    "operation": "remove_project_from_archive_data_block",
                    "user": self.u1.slug,
                    "args": {
                        "data_block": db1.slug
                    }
                }
            }
        ])

        worker.run_once_without_delete()

        # 4. Ensure streams have a None project and their slug is correct
        for stream in db1.streamids.all():
            assert stream.block == db1
            self.assertIsNone(stream.project)
            self.assertEqual(
                stream.slug,
                's--0000-0000--{0}--{1}'.format(
                    db1.formatted_gid,
                    IOTileVariableSlug(stream.var_lid).formatted_local_id()
                )
            )
            self.assertTrue(StreamData.objects.filter(stream_slug=stream.slug).count() > 0)
            self.assertEqual(StreamEventData.objects.filter(stream_slug=stream.slug).count(), 1)

    class BulkRemoveProjectsFromArchiveDataBlockTestCase(TestCase, TestMixin):
        def setUp(self):
            self.usersTestSetup()
            self.device_mocks = ThreeWaterMetersDeviceMocks()
            self.o2 = Org.objects.get(name='User Org')
            self.p1 = Project.objects.get(name='Project 1')
            self.pd1 = self.p1.devices.first()

        def tearDown(self):
            self.device_mocks.tearDown()
            self.userTestTearDown()

        def testRemoveProjectFromArchiveDataBlock(self):

            db1 = DataBlock.objects.create(org=self.o2, title='test1', device=self.pd1, block=1, created_by=self.u1)
            db2 = DataBlock.objects.create(org=self.o2, title='test2', device=self.pd1, block=2, created_by=self.u2)
            db3 = DataBlock.objects.create(org=self.o2, title='test3', device=self.pd2, block=3, created_by=self.u1)

            for db in [db1, db2, db3]:
                # 1. Archive data from devices into DataBlocks
                archive_action = ArchiveDeviceDataAction()
                archive_action._block = db
                archive_action._device = db.device
                archive_action.execute(arguments={'data_block_slug': db.slug})

                # 2. Manually set streams to refer a project, ensure work is done
                for stream in db.streamids.all():
                    assert stream.block == db
                    # stream.project = self.pd1.project
                    new_slug = IOTileStreamSlug()
                    new_slug.from_parts(
                        db.device.project.formatted_gid,
                        db.formatted_gid,
                        IOTileVariableSlug(stream.var_lid)
                    )
                    stream.slug = str(new_slug)
                    stream.save()
                    # self.assertIsNotNone(stream.project)
                    self.assertEqual(stream.slug,
                                     's--{0}--{1}--{2}'.format(
                                         db.device.project.formatted_gid,
                                         db.formatted_gid,
                                         IOTileVariableSlug(stream.var_lid).formatted_local_id()
                                     ))

            # 3. Execute worker to set the stream projects to 0
            queue = QueueTestMock()
            worker = Worker(queue, 2)

            queue.add_messages([
                {
                    "module": "apps.staff.worker.staff_operations",
                    "class": "StaffOperationsAction",
                    "arguments": {
                        "operation": "bulk_remove_project_from_archive_data_block",
                        "user": self.u1.slug,
                        "args": {
                            "data_blocks": [
                                db1.slug,
                                db2.slug,
                                db3.slug,
                                'b--0003-0000-0000-0555'  # Fake slug
                            ]
                        }
                    }
                }
            ])

            worker.run_once_without_delete()

            # 4. Ensure streams have a None project and their slug is correct
            for db in [db1, db2, db3]:
                for stream in db.streamids.all():
                    assert stream.block == db
                    self.assertIsNone(stream.project)
                    self.assertEqual(
                        stream.slug,
                        's--0000-0000--{0}--{1}'.format(
                            db.formatted_gid,
                            IOTileVariableSlug(stream.var_lid).formatted_local_id()
                        )
                    )


class UnclaimDeviceTestCase(TestCase, TestMixin):
    databases = '__all__'

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        #self.create_basic_test_devices()

    def tearDown(self):
        StreamId.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testUnclaimDeviceWithData(self):
        # Set up the users
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

        # Set up the project, device, and data
        project = self.p1

        d1 = Device.objects.create(id=1, project=project, org=project.org, template=self.dt1, created_by=self.u2    )

        v1 = StreamVariable.objects.create_variable(
            name='Var A', project=project, lid=1, created_by=self.u2
        )
        s1 = StreamId.objects.create_stream(project=project,
                                            device=d1,
                                            variable=v1,
                                            created_by=self.staff)
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
                                                    created_by=self.staff,
                                                    name='prop1', value=4)
        GenericProperty.objects.create_str_property(slug=d1.slug,
                                                    created_by=self.staff,
                                                    name='prop2', value='4')

        self.assertTrue(Device.objects.filter(slug=d1.slug).exists())
        self.assertEqual(Device.objects.filter(slug=d1.slug).first().project, d1.project)
        self.assertEqual(StreamVariable.objects.filter(project=project).count(), 1)
        self.assertEqual(StreamId.objects.filter(device=d1).count(), 1)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 2)
        self.assertEqual(GenericProperty.objects.filter(target=d1.slug).count(), 2)

        # Execute worker to unclaim the device
        queue = QueueTestMock()
        worker = Worker(queue, 2)

        queue.add_messages([
            {
                "module": "apps.staff.worker.staff_operations",
                "class": "StaffOperationsAction",
                "arguments": {
                    "operation": "unclaim_device",
                    "user": self.staff.slug,
                    "args": {
                        "device": d1.slug,
                        "clean_streams": False
                    }
                }
            }
        ])
        worker.run_once_without_delete()

        self.assertTrue(Device.objects.filter(slug=d1.slug).exists())
        device = Device.objects.get(slug=d1.slug)
        self.assertEqual(Device.objects.filter(slug=d1.slug).first().project, None)
        # Project level variables uneffected
        self.assertEqual(StreamVariable.objects.filter(project=project).count(), 1)
        # Streams and Stream Data uneffected (cleaned_streams=False)
        self.assertEqual(StreamId.objects.filter(device=d1).count(), 1)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 2)
        # Device Properties deleted
        self.assertEqual(GenericProperty.objects.filter(target=d1.slug).count(), 0)

        # Reclaim device
        ok = self.client.login(email='staff@acme.com', password='pass')
        self.assertTrue(ok)
        device_claim(device=d1, project=project, claimed_by=self.staff)

        self.assertTrue(Device.objects.filter(slug=d1.slug).exists())
        self.assertEqual(Device.objects.filter(slug=d1.slug).first().project, project)
        self.assertEqual(StreamVariable.objects.filter(project=project).count(), 1)
        self.assertEqual(StreamId.objects.filter(device=d1).count(), 1)

        # Execute worker to unclaim the device
        # This time, delete streams and stream data as well
        queue = QueueTestMock()
        worker = Worker(queue, 2)

        queue.add_messages([
            {
                "module": "apps.staff.worker.staff_operations",
                "class": "StaffOperationsAction",
                "arguments": {
                    "operation": "unclaim_device",
                    "user": self.u1.slug,
                    "args": {
                        "device": d1.slug,
                        'clean_streams': True
                    }
                }
            }
        ])
        worker.run_once_without_delete()

        self.assertTrue(Device.objects.filter(slug=d1.slug).exists())
        device = Device.objects.get(slug=d1.slug)
        self.assertEqual(Device.objects.filter(slug=d1.slug).first().project, None)
        self.assertEqual(StreamVariable.objects.filter(project=project).count(), 1)
        self.assertEqual(StreamId.objects.filter(device=d1).count(), 0)
        self.assertEqual(StreamData.objects.filter(stream_slug=s1.slug).count(), 0)
        self.assertEqual(GenericProperty.objects.filter(target=d1.slug).count(), 0)

        self.client.logout()
