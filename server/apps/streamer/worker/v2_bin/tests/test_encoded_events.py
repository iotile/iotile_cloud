import json
import os
from unittest import mock, skipIf

import dateutil.parser

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.physicaldevice.models import Device
from apps.sensorgraph.models import SensorGraph
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.models import StreamData
from apps.streamer.models import *
from apps.streamer.serializers import *
from apps.streamevent.models import StreamEventData
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import *
from apps.vartype.models import VarType, VarTypeDecoder

from ...common.test_utils import full_path

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')

class StreamerV2EncodedTestCase(TestMixin, APITestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=0x5001,
        )
        self.v2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p2, created_by=self.u3, lid=0x5002,
        )
        self.sg1 = SensorGraph.objects.create(name='SG 1', report_processing_engine_ver=2,
                                              created_by=self.u1, org=self.o1)
        self.pd1 = Device.objects.create_device(id=0xa, project=self.p1, label='d1', sg=self.sg1,
                                                template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(id=0xb, project=self.p2, label='d2', sg=self.sg1,
                                                template=self.dt1, created_by=self.u3)
        Streamer.objects.create(device=self.pd1, index=0, created_by=self.u2, selector=0x57FF, process_engine_ver=2)
        Streamer.objects.create(device=self.pd2, index=0, created_by=self.u3, selector=0x57FF, process_engine_ver=2)
        StreamId.objects.create_after_new_device(self.pd1)
        StreamId.objects.create_after_new_device(self.pd2)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()
        self.s2 = StreamId.objects.filter(variable=self.v2).first()

    def tearDown(self):
        StreamData.objects.all().delete()
        Streamer.objects.all().delete()
        StreamerReport.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def _create_encoded_stream(self):
        device = Device.objects.create_device(id=0x235, project=self.p1, label='d1', sg=self.sg1,
                                              template=self.dt1, created_by=self.u2)
        Streamer.objects.create(device=device, index=0, created_by=self.u2, selector=0xd7ff, process_engine_ver=2)
        var_type = VarType.objects.create(
            name='Accelerometer',
            storage_units_full='Encoded',
            created_by=self.u1
        )
        VarTypeDecoder.objects.create(var_type=var_type, created_by=self.u1,
                                      raw_packet_format='<LLLL',
                                      packet_info={
                                          'decoding': [
                                              "H{axis:2,peak:14}",
                                              "H{duration}",
                                              "l{delta_v_x}",
                                              "l{delta_v_y}",
                                              "l{delta_v_z}",
                                          ],
                                          "transform": {
                                              "axis": {
                                                  "map": {
                                                      "0": "x",
                                                      "1": "y",
                                                      "2": "z"
                                                  }
                                              },
                                              "peak": {
                                                  "mdo": [49, 1000, 0.0]
                                              },
                                              "delta_v_x": {
                                                  "mdo": [1, 65536, 0.0]
                                              },
                                              "delta_v_y": {
                                                  "mdo": [1, 65536, 0.0]
                                              },
                                              "delta_v_z": {
                                                  "mdo": [1, 65536, 0.0]
                                              }
                                          }
                                      })
        self.assertIsNotNone(var_type.decoder)
        variable = StreamVariable.objects.create_variable(
            name='Event', project=self.p2, created_by=self.u3, lid=0x5020, var_type=var_type
        )
        stream = StreamId.objects.create(device=device, variable=variable, project=self.p1, var_type=var_type,
                                     created_by=self.u2, mdo_type = 'S')
        return stream


    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testEncodedEvents(self, mock_download_s3):

        stream = self._create_encoded_stream()

        url = reverse('streamerreport-list')

        test_filename = full_path('new_combined_selector.bin')

        url += '?timestamp={0}'.format('2016-09-28T10:00:00Z')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)
        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            response = self.client.post(url, {'file': fp}, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Streamer.objects.count(), 3)
        self.assertEqual(StreamerReport.objects.count(), 1)
        self.assertEqual(StreamData.objects.count(), 13)
        self.assertEqual(StreamData.objects.filter(stream_slug=stream.slug).count(), 12)
        self.assertEqual(StreamEventData.objects.count(), 2)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream.slug).count(), 2)

        event = StreamEventData.objects.filter(stream_slug=stream.slug).first()
        self.assertEqual(event.extra_data['axis'], 'z')
        self.assertEqual(event.extra_data['peak'], 32 * 49 / 1000)
        self.assertEqual(event.extra_data['duration'], 12)
        self.assertEqual(event.extra_data['delta_v_x'], 4743 / 65536)
        self.assertEqual(event.extra_data['delta_v_y'], 3877 / 65536)
        self.assertEqual(event.extra_data['delta_v_z'], -9556 / 65536)

        point = StreamData.objects.filter(stream_slug=stream.slug).first()
        self.assertEqual(point.timestamp, event.timestamp)
        self.assertEqual(point.device_timestamp, event.device_timestamp)
        for point in StreamData.objects.filter(stream_slug=stream.slug):
            self.assertEqual(point.status, 'cln')

        self.assertEqual(event.status, 'cln')

        self.client.logout()

        device_status = stream.device.status
        report = StreamerReport.objects.first()
        self.assertIsNotNone(status)
        self.assertEqual(device_status.last_report_ts, report.sent_timestamp)
        last_data = StreamData.objects.filter(stream_slug=stream.slug).order_by('streamer_local_id').last()
        self.assertEqual(device_status.last_known_id, last_data.streamer_local_id)


