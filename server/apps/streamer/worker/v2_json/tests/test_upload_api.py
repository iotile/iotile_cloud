import json
import os
import dateutil.parser
from unittest import skipIf, mock

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils.dateparse import parse_datetime
from django.core.files.uploadedfile import SimpleUploadedFile

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.stream.models import StreamVariable, StreamId
from apps.sensorgraph.models import SensorGraph
from apps.physicaldevice.models import Device
from apps.utils.timezone_utils import *
from apps.streamer.models import *
from apps.streamer.serializers import *
from apps.sqsworker.workerhelper import Worker
from apps.sqsworker.tests import QueueTestMock
from apps.utils.iotile.streamer import STREAMER_SELECTOR

from ...common.test_utils import *

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')


class StreamerV2JsonAPITestCase(TestMixin, APITestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=0x5020,
        )
        self.v2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p2, created_by=self.u3, lid=0x5002,
        )
        self.sg = SensorGraph.objects.create_graph(name='SG1', report_processing_engine_ver=2,
                                                   created_by=self.u2, org=self.o1)
        self.pd1 = Device.objects.create_device(id=0xa, project=self.p1, sg=self.sg, label='d1',
                                                template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(id=0xb, project=self.p2, sg=self.sg, label='d2',
                                                template=self.dt1, created_by=self.u3)
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

    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testJsonReportUpload(self, mock_download_s3):

        url = reverse('streamerreport-list')

        test_filename = full_path('v2_report1.json')

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            response = self.client.post(url, {'file': fp}, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
            fp.close()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            response = self.client.post(url, {'file': fp}, format='multipart')
            # 400 if no ?timestamp=
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            fp.close()

        url += '?timestamp={0}'.format('2016-09-28T10:00:00Z')

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            response = self.client.post(url, {'file': fp}, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            deserialized = json.loads(response.content.decode())
            self.assertEqual(deserialized['count'], 2)
            fp.close()

        self.assertEqual(Streamer.objects.count(), 1)
        self.assertEqual(StreamerReport.objects.count(), 1)

        self.assertEqual(StreamEventData.objects.count(), 2)

        streamer = Streamer.objects.first()
        streamer_report = StreamerReport.objects.first()

        self.assertEqual(streamer_report.streamer.id, streamer.id)
        self.assertEqual(streamer_report.original_first_id, 2)
        self.assertEqual(streamer_report.original_last_id, 3)
        self.assertEqual(streamer_report.actual_first_id, 2)
        self.assertEqual(streamer_report.actual_last_id, 3)
        self.assertEqual(streamer.last_id, 3)

        self.client.logout()

    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    @mock.patch('apps.streamevent.helpers.upload_json_data_from_object')
    def testJsonReportUploadIssue1296(self, mock_upload_json, mock_download_s3):
        mock_upload_json.return_value = True
        url = reverse('streamerreport-list')

        test_filename = full_path('v2_report2.mp')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        url += '?timestamp={0}'.format('2016-09-28T10:00:00Z')

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            response = self.client.post(url, {'file': fp}, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            deserialized = json.loads(response.content.decode())
            self.assertEqual(deserialized['count'], 2)
            fp.close()

        self.assertEqual(Streamer.objects.count(), 1)
        self.assertEqual(StreamerReport.objects.count(), 1)

        self.assertEqual(StreamEventData.objects.count(), 2)

        streamer = Streamer.objects.first()
        streamer_report = StreamerReport.objects.first()

        self.assertEqual(streamer_report.streamer.id, streamer.id)
        self.assertEqual(streamer_report.original_first_id, 1179649)
        self.assertEqual(streamer_report.original_last_id, 1179650)
        self.assertEqual(streamer_report.actual_first_id, 1179649)
        self.assertEqual(streamer_report.actual_last_id, 1179650)
        self.assertEqual(streamer.last_id, 1179650)

        self.client.logout()

    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testMsgPackReportUpload(self, mock_download_s3):

        url = reverse('streamerreport-list')

        test_filename = full_path('v2_report1.mp')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        url += '?timestamp={0}'.format('2016-09-28T10:00:00Z')

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            response = self.client.post(url, {'file': fp}, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            deserialized = json.loads(response.content.decode())
            self.assertEqual(deserialized['count'], 2)
            fp.close()

        self.assertEqual(Streamer.objects.count(), 1)
        self.assertEqual(StreamerReport.objects.count(), 1)

        self.assertEqual(StreamEventData.objects.count(), 2)

        streamer = Streamer.objects.first()
        streamer_report = StreamerReport.objects.first()

        self.assertEqual(streamer_report.streamer.id, streamer.id)
        self.assertEqual(streamer_report.original_first_id, 2)
        self.assertEqual(streamer_report.original_last_id, 3)
        self.assertEqual(streamer_report.actual_first_id, 2)
        self.assertEqual(streamer_report.actual_last_id, 3)
        self.assertEqual(streamer.last_id, 3)

        self.client.logout()
