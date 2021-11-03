from django.test import TestCase
from django.utils import timezone

from apps.project.models import Project
from apps.utils.test_util import TestMixin
# from apps.utils.gid.convert import *
from apps.stream.models import StreamId, StreamVariable
from apps.property.models import GenericProperty
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.streamnote.models import StreamNote

from ..claim_utils import *
from ..models import *


class DeviceUtilsTestCase(TestMixin, TestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        GenericProperty.objects.all().delete()
        Device.objects.all().delete()
        StreamVariable.objects.all().delete()
        StreamId.objects.all().delete()
        self.orgTestTearDown()
        self.userTestTearDown()
        self.deviceTemplateTestTearDown()

    def testDeviceSemiClaimUnclaim(self):
        sg = self.createTestSensorGraph()
        d1 = Device.objects.create(id=1, label="d1", template=self.dt1, sg=sg, created_by=self.u1)

        device_semiclaim(device=d1, org=self.o2)
        d1 = Device.objects.get(pk=1)
        self.assertEqual(d1.org, self.o2)

    def testDeviceClaimUnclaim(self):
        sg = self.createTestSensorGraph()
        d1 = Device.objects.create(id=1, label="d1", template=self.dt1, sg=sg, created_by=self.u1)
        p1 = Project.objects.create(name='Project 1', project_template=self.pt1,
                                         created_by=self.u2, org=self.o2)

        device_claim(device=d1, project=p1, claimed_by=self.u2)
        d1 = Device.objects.get(pk=1)
        self.assertEqual(d1.project, p1)
        self.assertEqual(d1.org, p1.org)
        self.assertEqual(d1.claimed_by, self.u2)
        self.assertEqual(d1.streamids.count(), 2)

        device_unclaim(device=d1, label='Unclaim 1', clean_streams=True)
        d1 = Device.objects.get(pk=1)
        self.assertIsNone(d1.project)
        self.assertIsNone(d1.org)
        self.assertIsNone(d1.claimed_by)
        self.assertEqual(d1.streamids.count(), 0)

    def testDeviceUnclaimWithData(self):
        sg = self.createTestSensorGraph()
        d1 = Device.objects.create(id=1, label="d1", template=self.dt1, sg=sg, created_by=self.u1)
        p1 = Project.objects.create(name='Project 1', project_template=self.pt1,
                                         created_by=self.u2, org=self.o2)

        device_claim(device=d1, project=p1, claimed_by=self.u2)
        d1 = Device.objects.get(pk=1)
        self.assertEqual(d1.streamids.count(), 2)
        s5001 = d1.streamids.get(var_lid=0x5001)
        StreamData.objects.create(
            stream_slug=s5001.slug,
            type='ITR',
            timestamp=timezone.now(),
            streamer_local_id=5,
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=s5001.slug,
            type='ITR',
            timestamp=timezone.now(),
            streamer_local_id=6,
            int_value=6
        )
        s5002 = d1.streamids.get(var_lid=0x5002)
        StreamEventData.objects.create(
            timestamp=timezone.now(),
            device_timestamp=10,
            stream_slug=s5002.slug,
            streamer_local_id=2
        )
        StreamEventData.objects.create(
            timestamp=timezone.now(),
            device_timestamp=10,
            stream_slug=s5002.slug,
            streamer_local_id=3
        )
        StreamNote.objects.create(
            target_slug=d1.slug,
            timestamp=timezone.now(),
            created_by=self.u2,
            note='System 1',
            type='sc'
        )
        StreamNote.objects.create(
            target_slug=s5001.slug,
            timestamp=timezone.now(),
            created_by=self.u2,
            note='Note 2'
        )
        StreamNote.objects.create(
            target_slug=d1.slug,
            timestamp=timezone.now(),
            created_by=self.u2,
            note='Note 3'
        )
        DeviceLocation.objects.create(
            timestamp=timezone.now(),
            target_slug=d1.slug,
            lat=12.1234, lon=10.000,
            user=self.u2
        )
        DeviceLocation.objects.create(
            timestamp=timezone.now(),
            target_slug=d1.slug,
            lat=12.1234, lon=11.000,
            user=self.u2
        )

        self.assertEqual(StreamData.objects.count(), 2)
        self.assertEqual(StreamEventData.objects.count(), 2)
        self.assertEqual(StreamNote.objects.count(), 3)
        self.assertEqual(DeviceLocation.objects.count(), 2)

        device_unclaim(device=d1, label='Unclaim 1', clean_streams=False)
        d1 = Device.objects.get(pk=1)
        self.assertEqual(StreamData.objects.count(), 2)
        self.assertEqual(StreamEventData.objects.count(), 2)
        self.assertEqual(StreamNote.objects.count(), 2)
        self.assertEqual(DeviceLocation.objects.count(), 0)

        device_claim(device=d1, project=p1, claimed_by=self.u2)
        device_unclaim(device=d1, label='Unclaim 1', clean_streams=True)
        d1 = Device.objects.get(pk=1)
        self.assertEqual(StreamData.objects.count(), 0)
        self.assertEqual(StreamEventData.objects.count(), 0)
        self.assertEqual(StreamNote.objects.count(), 1)
        self.assertEqual(DeviceLocation.objects.count(), 0)
