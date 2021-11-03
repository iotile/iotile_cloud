import json
import os
import dateutil.parser
from unittest import skipIf, mock

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.conf import settings

from apps.utils.test_util import TestMixin
from apps.streamdata.models import StreamData
from apps.physicaldevice.models import Device
from apps.utils.timezone_utils import *
from apps.streamer.serializers import *
from apps.sensorgraph.models import SensorGraph
from apps.utils.iotile.variable import SYSTEM_VID
from apps.ota.models import DeploymentRequest, DeploymentAction, DeviceScript, DeviceVersionAttribute
from apps.devicetemplate.models import DeviceTemplate
from apps.streamnote.models import StreamNote

from ..utils.streamer import DeploymentActionStreamerHelper

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')

class OTAStreamerProcessingTestCase(TestMixin, TestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.sg1 = SensorGraph.objects.create(name='SG 1 v0.1', report_processing_engine_ver=2,
                                              app_tag=1024, app_major_version=0, app_minor_version=1,
                                              created_by=self.u1, org=self.o1)
        self.assertIsNotNone(self.p1)
        self.pd1 = Device.objects.create_device(id=0xa, project=self.p1, sg=self.sg1, label='d1', template=self.dt1, created_by=self.u2)

        DeviceTemplate.objects.create(external_sku='Device 2048 V1.1',
                                      os_tag=2048, os_major_version=0, os_minor_version=1,
                                      major_version=1, minor_version=1, released_on=timezone.now(),
                                      created_by=self.u2, org=self.o2)
        self.new_dt = DeviceTemplate.objects.create(external_sku='Device 2048 V1.2',
                                                    os_tag=2048, os_major_version=1, os_minor_version=0,
                                                    major_version=1,  minor_version=2, released_on=timezone.now(),
                                                    created_by=self.u2, org=self.o2)

        SensorGraph.objects.create(name='SG 2048 V1',
                                   app_tag=2048, app_major_version=0, app_minor_version=1,
                                   major_version=1, minor_version=0,
                                   created_by=self.u2, org=self.o1)
        self.new_sg = SensorGraph.objects.create(name='SG 2048 V2',
                                                 app_tag=2048, app_major_version=1, app_minor_version=0,
                                                 major_version=2, minor_version=0,
                                                 created_by=self.u2, org=self.o1)

    def tearDown(self):
        StreamData.objects.all().delete()
        DeviceScript.objects.all().delete()
        DeploymentRequest.objects.all().delete()
        DeploymentAction.objects.all().delete()
        Device.objects.all().delete()
        StreamNote.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def test_ota_os_tag(self):
        device_template = self.pd1.template
        self.assertEqual(device_template.os_tag, 1024)

        ds1 = DeviceScript.objects.create(
            name='script 1',
            org=self.o1,
            major_version=2, minor_version=4, patch_version=0,
            created_by=self.u1,
            released=True,
        )
        deployment_request = DeploymentRequest.objects.create(
            script=ds1,
            org=self.pd1.org,
            selection_criteria=['os_tag:eq:1024'],
            released_on=timezone.now()
        )
        deployment_action = DeploymentAction.objects.create(
            deployment=deployment_request,
            attempt_successful=True,
            device=self.pd1
        )
        self.assertFalse(deployment_action.device_confirmation)

        os_tag_stream = str(self.pd1.get_stream_slug_for(SYSTEM_VID['OS_TAG_VERSION']))

        data = StreamData.objects.create(
            stream_slug=os_tag_stream,
            device_timestamp=40,
            timestamp=timezone.now(),
            streamer_local_id=10,
            int_value = 0x04000800
        )

        helper = DeploymentActionStreamerHelper(self.pd1)
        helper.complete_action(SYSTEM_VID['OS_TAG_VERSION'], data)

        device_template = self.pd1.template
        self.assertEqual(device_template, self.new_dt)
        self.assertEqual(device_template.os_tag, 2048)

        deployment_action = DeploymentAction.objects.get(
            deployment=deployment_request,
            attempt_successful=True,
            device=self.pd1
        )
        self.assertTrue(deployment_action.device_confirmation)

        version = DeviceVersionAttribute.objects.current_device_version_qs(self.pd1).last()
        self.assertIsNotNone(version)
        self.assertEqual(version.type, 'os')
        self.assertEqual(version.tag, 2048)
        self.assertEqual(version.major_version, 1)
        self.assertEqual(version.minor_version, 0)
        self.assertEqual(version.updated_ts, data.timestamp)

        self.assertEqual(StreamNote.objects.filter(target_slug=self.pd1.slug).count(), 1)

    def test_ota_app_tag(self):
        sg = self.pd1.sg
        self.assertEqual(sg.app_tag, 1024)

        ds1 = DeviceScript.objects.create(
            name='script 1',
            org=self.o1,
            major_version=2, minor_version=4, patch_version=0,
            created_by=self.u1,
            released=True,
        )
        deployment_request = DeploymentRequest.objects.create(
            script=ds1,
            org=self.pd1.org,
            selection_criteria=['app_tag:eq:1024'],
            released_on=timezone.now()
        )
        deployment_action = DeploymentAction.objects.create(
            deployment=deployment_request,
            attempt_successful=True,
            device=self.pd1
        )
        self.assertFalse(deployment_action.device_confirmation)

        app_tag_stream = str(self.pd1.get_stream_slug_for(SYSTEM_VID['APP_TAG_VERSION']))

        data = StreamData.objects.create(
            stream_slug=app_tag_stream,
            device_timestamp=40,
            timestamp=timezone.now(),
            streamer_local_id=10,
            int_value = 0x04000800
        )

        helper = DeploymentActionStreamerHelper(self.pd1)
        helper.complete_action(SYSTEM_VID['APP_TAG_VERSION'], data)

        sg = self.pd1.sg
        self.assertEqual(sg, self.new_sg)
        self.assertEqual(sg.app_tag, 2048)

        deployment_action = DeploymentAction.objects.get(
            deployment=deployment_request,
            attempt_successful=True,
            device=self.pd1
        )
        self.assertTrue(deployment_action.device_confirmation)

        version = DeviceVersionAttribute.objects.current_device_version_qs(self.pd1).last()
        self.assertIsNotNone(version)
        self.assertEqual(version.type, 'app')
        self.assertEqual(version.tag, 2048)
        self.assertEqual(version.major_version, 1)
        self.assertEqual(version.minor_version, 0)
        self.assertEqual(version.updated_ts, data.timestamp)

        self.assertEqual(StreamNote.objects.filter(target_slug=self.pd1.slug).count(), 1)

    def test_ota_tag_no_deployment_action(self):
        device_template = self.pd1.template
        self.assertEqual(device_template.os_tag, 1024)

        ds1 = DeviceScript.objects.create(
            name='script 1',
            org=self.o1,
            major_version=2, minor_version=4, patch_version=0,
            created_by=self.u1,
            released=True,
        )
        deployment_request = DeploymentRequest.objects.create(
            script=ds1,
            org=self.pd1.org,
            selection_criteria=['os_tag:eq:1024'],
            released_on=timezone.now()
        )

        os_tag_stream = str(self.pd1.get_stream_slug_for(SYSTEM_VID['OS_TAG_VERSION']))

        data = StreamData.objects.create(
            stream_slug=os_tag_stream,
            device_timestamp=40,
            timestamp=timezone.now(),
            streamer_local_id=10,
            int_value = 0x04000800
        )

        helper = DeploymentActionStreamerHelper(self.pd1)
        helper.complete_action(SYSTEM_VID['OS_TAG_VERSION'], data)

        device_template = self.pd1.template
        self.assertEqual(device_template, self.new_dt)
        self.assertEqual(device_template.os_tag, 2048)

        deployment_action = DeploymentAction.objects.get(
            deployment=deployment_request,
            attempt_successful=True,
            device=self.pd1
        )
        self.assertIsNotNone(deployment_action)
        self.assertTrue(deployment_action.device_confirmation)
        self.assertTrue(deployment_action.attempt_successful)

        version = DeviceVersionAttribute.objects.current_device_version_qs(self.pd1).last()
        self.assertIsNotNone(version)
        self.assertEqual(version.type, 'os')
        self.assertEqual(version.tag, 2048)
        self.assertEqual(version.major_version, 1)
        self.assertEqual(version.minor_version, 0)
        self.assertEqual(version.updated_ts, data.timestamp)

    def test_ota_tag_no_deployment_request_or_action(self):
        device_template = self.pd1.template
        self.assertEqual(device_template.os_tag, 1024)

        os_tag_stream = str(self.pd1.get_stream_slug_for(SYSTEM_VID['OS_TAG_VERSION']))

        data = StreamData.objects.create(
            stream_slug=os_tag_stream,
            device_timestamp=40,
            timestamp=timezone.now(),
            streamer_local_id=10,
            int_value = 0x04000800
        )

        helper = DeploymentActionStreamerHelper(self.pd1)
        helper.complete_action(SYSTEM_VID['OS_TAG_VERSION'], data)

        device_template = self.pd1.template
        self.assertEqual(device_template, self.new_dt)
        self.assertEqual(device_template.os_tag, 2048)

        deployment_action_qs = DeploymentAction.objects.filter(
            device=self.pd1
        )
        self.assertEqual(deployment_action_qs.count(), 0)

        version = DeviceVersionAttribute.objects.current_device_version_qs(self.pd1).last()
        self.assertIsNotNone(version)
        self.assertEqual(version.type, 'os')
        self.assertEqual(version.tag, 2048)
        self.assertEqual(version.major_version, 1)
        self.assertEqual(version.minor_version, 0)
        self.assertEqual(version.updated_ts, data.timestamp)

