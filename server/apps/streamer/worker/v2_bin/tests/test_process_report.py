import json
import os
from unittest import mock, skipIf

import dateutil.parser

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.devicetemplate.models import DeviceTemplate
from apps.ota.models import DeploymentAction, DeploymentRequest, DeviceScript, DeviceVersionAttribute
from apps.physicaldevice.models import Device
from apps.sensorgraph.models import SensorGraph
from apps.sqsworker.exceptions import WorkerActionHardError
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.helpers import StreamDataBuilderHelper
from apps.streamdata.models import StreamData
from apps.streamer.models import *
from apps.streamer.serializers import *
from apps.streamevent.models import StreamEventData
from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import *
from apps.vartype.models import VarType

from ...common.test_utils import create_test_data
from ..process_report import ProcessReportV2Action

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')

class StreamerV2ReportProcessingTestCase(TestMixin, TestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.sg1 = SensorGraph.objects.create(name='SG 1', report_processing_engine_ver=2, app_tag=1024,
                                              created_by=self.u1, org=self.o1)
        self.assertIsNotNone(self.p1)
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=0x5001,
        )
        self.pd1 = Device.objects.create_device(id=0xa, project=self.p1, sg=self.sg1, label='d1', template=self.dt1, created_by=self.u2)
        StreamId.objects.create_after_new_device(self.pd1)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()

    def tearDown(self):
        StreamData.objects.all().delete()
        Streamer.objects.all().delete()
        StreamerReport.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        DeviceScript.objects.all().delete()
        DeploymentRequest.objects.all().delete()
        DeploymentAction.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def _create_stream(self, device):
        var_type = VarType.objects.create(
            name='Accelerometer',
            storage_units_full='Event',
            stream_data_type='E2',
            created_by=self.u1
        )
        variable = StreamVariable.objects.create_variable(
            name='Event', project=self.p2, created_by=self.u3, lid=0x5020, var_type=var_type
        )
        stream = StreamId.objects.create(
            device=device, variable=variable, project=self.p1, var_type=var_type, data_type='E2',
            created_by=self.u2, mdo_type = 'S'
        )
        return stream

    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def test_data_pointer_to_events(self, mock_download_s3):

        device = Device.objects.create_device(id=0x235, project=self.p1, label='d1', sg=self.sg1,
                                              template=self.dt1, created_by=self.u2)
        streamer = Streamer.objects.create(device=device, index=0, created_by=self.u2, selector=0xd7ff, process_engine_ver=2)
        stream = self._create_stream(device)

        action = ProcessReportV2Action()
        action._received_dt = parse_datetime('2016-09-28T10:00:00Z')
        action._streamer = streamer
        action._device = device
        action._streamer_report = StreamerReport.objects.create(streamer=streamer,
                                                                original_first_id=5,
                                                                original_last_id=9,
                                                                device_sent_timestamp=120,
                                                                sent_timestamp=action._received_dt,
                                                                incremental_id=10,
                                                                created_by=self.u1 )

        event1 = StreamEventData.objects.create(
            timestamp=timezone.now(),
            stream_slug=stream.slug,
            streamer_local_id=5
        )
        StreamEventData.objects.create(
            timestamp=timezone.now(),
            stream_slug=stream.slug,
            streamer_local_id=7
        )

        helper = StreamDataBuilderHelper()
        stream_payload = [
            (stream.slug, 10, 5),
            (stream.slug, 20, 6),
            (stream.slug, 30, 7),
            (stream.slug, 40, 8),
            (stream.slug, 50, 9),
        ]
        action._data_entries = create_test_data(helper, stream_payload, 5)

        self.assertNotEqual(event1.timestamp, action._data_entries[0].timestamp)
        self.assertNotEqual(event1.device_timestamp, action._data_entries[0].device_timestamp)

        self.assertEqual(len(action._data_entries), 5)
        action._data_builder = helper
        action._handle_reboots_if_needed()
        action._syncup_e2_data()

        event1 = StreamEventData.objects.first()
        self.assertEqual(event1.timestamp, action._data_entries[0].timestamp)
        self.assertEqual(event1.device_timestamp, action._data_entries[0].device_timestamp)

        event2 = StreamEventData.objects.last()
        self.assertEqual(event2.timestamp, action._data_entries[2].timestamp)
        self.assertEqual(event2.device_timestamp, action._data_entries[2].device_timestamp)

    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def test_action_user_is_streamer_report_creator(self, mock_download_s3):

        device = Device.objects.create_device(id=0x235, project=self.p1, label='d1', sg=self.sg1,
                                              template=self.dt1, created_by=self.u2)
        streamer = Streamer.objects.create(device=device, index=0, created_by=self.u2, selector=0xd7ff, process_engine_ver=2)
        stream = self._create_stream(device)

        action = ProcessReportV2Action()
        action._received_dt = parse_datetime('2016-09-28T10:00:00Z')
        action._streamer = streamer
        action._device = device
        action._streamer_report = StreamerReport.objects.create(streamer=streamer,
                                                                original_first_id=5,
                                                                original_last_id=9,
                                                                device_sent_timestamp=120,
                                                                sent_timestamp=action._received_dt,
                                                                incremental_id=10,
                                                                created_by=self.u1 )

        bucket, key = action._streamer_report.get_dropbox_s3_bucket_and_key()

        args = {
            'version': 'v{}'.format(streamer.process_engine_ver),
            'streamer': streamer.slug,
            'bucket': bucket,
            'key': key
        }

        self.assertEqual(action._user, None)
        try:
            action.execute(args)
        # There should be an error because the parser can't parse a mocked file
        except WorkerActionHardError:
            pass
        # Check that action._user can be used to call filter_helper.process_filter_report
        self.assertEqual(action._user, self.u1)

    def test_ota_os_tag(self):
        device_template = self.pd1.template
        self.assertEqual(device_template.os_tag, 1024)
        DeviceTemplate.objects.create(external_sku='Device 2048 V0.1',
                                      os_tag=2048, os_major_version=0, os_minor_version=1,
                                      major_version=0, minor_version=1, released_on=timezone.now(),
                                      created_by=self.u2, org=self.o2)
        new_template = DeviceTemplate.objects.create(external_sku='Device 2048 V1.0',
                                                     os_tag=2048, os_major_version=1, os_minor_version=0,
                                                     major_version=1,  minor_version=0, released_on=timezone.now(),
                                                     created_by=self.u2, org=self.o2)

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


        action = ProcessReportV2Action()
        action._received_dt = parse_datetime('2016-09-28T10:00:00Z')

        action._streamer = Streamer.objects.create(device=self.pd1,
                                                   index=0,
                                                   created_by=self.u2,
                                                   selector=STREAMER_SELECTOR['SYSTEM'],
                                                   process_engine_ver=2)

        action._device = self.pd1
        action._streamer_report = StreamerReport.objects.create(streamer=action._streamer,
                                                                original_first_id=5,
                                                                original_last_id=9,
                                                                device_sent_timestamp=120,
                                                                sent_timestamp=action._received_dt,
                                                                incremental_id=10,
                                                                created_by=self.u1 )

        os_tag_stream = str(self.pd1.get_stream_slug_for(SYSTEM_VID['OS_TAG_VERSION']))

        helper = StreamDataBuilderHelper()
        stream_payload = [
            (self.s1.slug, 10, 5),
            (os_tag_stream, 40, 0x04000800),
            (self.s1.slug, 50, 9),
        ]
        action._data_entries = create_test_data(helper, stream_payload, 5)
        # Update data with proper timestamps
        for d in action._data_entries:
            d.timestamp = timezone.now() - datetime.timedelta(days=1) + datetime.timedelta(seconds=d.device_timestamp)
            d.save()
        self.assertEqual(len(action._data_entries), 3)
        action._process_ota_data()

        device_template = self.pd1.template
        self.assertEqual(device_template, new_template)
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
        self.assertEqual(version.updated_ts, action._data_entries[1].timestamp)

    def test_ota_app_tag(self):
        sg = self.pd1.sg
        self.assertEqual(sg.app_tag, 1024)
        SensorGraph.objects.create(name='SG 2048 V0.1',
                                   app_tag=2048, app_major_version=0, app_minor_version=1,
                                   major_version=0, minor_version=1,
                                   created_by=self.u2, org=self.o1)
        new_sg = SensorGraph.objects.create(name='SG 2048 V1.0',
                                            app_tag=2048, app_major_version=1, app_minor_version=0,
                                            major_version=1, minor_version=0,
                                            created_by=self.u2, org=self.o1)


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


        action = ProcessReportV2Action()
        action._received_dt = parse_datetime('2016-09-28T10:00:00Z')

        action._streamer = Streamer.objects.create(device=self.pd1,
                                                   index=0,
                                                   created_by=self.u2,
                                                   selector=STREAMER_SELECTOR['SYSTEM'],
                                                   process_engine_ver=2)

        action._device = self.pd1
        action._streamer_report = StreamerReport.objects.create(streamer=action._streamer,
                                                                original_first_id=5,
                                                                original_last_id=9,
                                                                device_sent_timestamp=120,
                                                                sent_timestamp=action._received_dt,
                                                                incremental_id=10,
                                                                created_by=self.u1 )

        app_tag_stream = str(self.pd1.get_stream_slug_for(SYSTEM_VID['APP_TAG_VERSION']))

        helper = StreamDataBuilderHelper()
        stream_payload = [
            (self.s1.slug, 10, 5),
            (app_tag_stream, 40, 0x04000800),
            (self.s1.slug, 50, 9),
        ]
        action._data_entries = create_test_data(helper, stream_payload, 5)
        # Update data with proper timestamps
        for d in action._data_entries:
            d.timestamp = timezone.now() - datetime.timedelta(days=1) + datetime.timedelta(seconds=d.device_timestamp)
            d.save()
        self.assertEqual(len(action._data_entries), 3)
        action._process_ota_data()

        sg = self.pd1.sg
        self.assertEqual(sg, new_sg)
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
        self.assertEqual(version.updated_ts, action._data_entries[1].timestamp)

    def test_handle_trip_system_data(self):
        device = Device.objects.create_device(id=0x053e, project=self.p1, label='d1', sg=self.sg1,
                                              template=self.dt1, created_by=self.u2)
        streamer = Streamer.objects.create(device=device, index=2, created_by=self.u2, selector=0x0fff, process_engine_ver=2)
        stream = self._create_stream(device)

        action = ProcessReportV2Action()
        action._received_dt = parse_datetime('2019-07-25T14:39:14Z')
        action._streamer = streamer
        action._device = device
        action._streamer_report = StreamerReport.objects.create(streamer=streamer,
                                                                original_first_id=1008,
                                                                original_last_id=1703,
                                                                device_sent_timestamp=63371,
                                                                sent_timestamp=action._received_dt,
                                                                incremental_id=1708,
                                                                created_by=self.u1 )

        helper = StreamDataBuilderHelper()
        trip_start_slug = str(device.get_stream_slug_for('0e00'))
        trip_end_slug = str(device.get_stream_slug_for('0e01'))
        trip_record_slug = str(device.get_stream_slug_for('0e02'))
        stream_payload = [
            (trip_start_slug, 978, 1563844954),
            (trip_record_slug, 978, 1),
            (trip_record_slug, 2764705920, 0),
            (trip_end_slug, 2764705921, 1563907078),
        ]
        action._data_entries = create_test_data(helper, stream_payload, 1008)

        self.assertEqual(len(action._data_entries), 4)
        action._data_builder = helper
        action._handle_reboots_if_needed()

        self.assertEqual(str(action._data_entries[0].status), 'utc')
        self.assertEqual(str(action._data_entries[1].status), 'cln')
        self.assertEqual(str(action._data_entries[2].status), 'utc')
        self.assertEqual(str(action._data_entries[3].status), 'utc')

        self.assertEqual(str(action._data_entries[0].timestamp), '2019-07-23 01:22:34+00:00')
        self.assertEqual(str(action._data_entries[1].timestamp), '2019-07-23 01:22:34+00:00')
        self.assertEqual(str(action._data_entries[2].timestamp), '2019-07-23 18:37:52+00:00')
        self.assertEqual(str(action._data_entries[3].timestamp), '2019-07-23 18:37:58+00:00')
