import json
import os
from unittest import skipIf, mock
import dateutil.parser
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin
from apps.stream.models import StreamVariable, StreamId
from apps.streamdata.models import StreamData
from apps.sensorgraph.models import SensorGraph
from apps.physicaldevice.models import Device
from apps.utils.timezone_utils import *
from apps.streamer.models import *
from apps.streamer.serializers import *
from ...common.test_utils import *

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')

class StreamerV1TestCase(TestMixin, APITestCase):

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
        sg1 = SensorGraph.objects.create(name='SG 1', report_processing_engine_ver=1,
                                         created_by=self.u1, org=self.o1)
        self.pd1 = Device.objects.create_device(id=0xa, project=self.p1, label='d1', sg=sg1,
                                                template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(id=0xb, project=self.p2, label='d2', sg=sg1,
                                                template=self.dt1, created_by=self.u3)
        Streamer.objects.create(device=self.pd1, index=0, created_by=self.u2, selector=0x57FF, process_engine_ver=1)
        Streamer.objects.create(device=self.pd2, index=0, created_by=self.u3, selector=0x57FF, process_engine_ver=1)
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

    @mock.patch('apps.streamer.worker.common.base_action.ProcessReportBaseAction.schedule')
    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testReportUpload(self, mock_download_s3, mock_process_report_schedule):

        url = reverse('streamerreport-list')

        test_filename = full_path('valid_100_readings.bin')

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            response = self.client.post(url, {'file': fp}, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            response = self.client.post(url, {'file': fp}, format='multipart')
            # 400 if no ?timestamp=
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        url += '?timestamp={0}'.format('2016-09-28T10:00:00Z')

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            response = self.client.post(url, {'file': fp}, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(Streamer.objects.count(), 2)
            self.assertEqual(StreamerReport.objects.count(), 1)

        self.client.logout()

    @mock.patch('apps.streamer.worker.common.base_action.ProcessReportBaseAction.schedule')
    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testUploadBadTimestamp(self, mock_download_s3, mock_process_report_schedule):

        url = reverse('streamerreport-list')

        test_filename = full_path('valid_16_readings.bin')
        self.s1.input_unit = None
        self.s1.save()

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            ok = self.client.login(email='user1@foo.com', password='pass')
            self.assertTrue(ok)

            data = {
                'file': fp,
            }
            response = self.client.post(url, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

            url1 = url + '?timestamp={0}'.format('2017-01-10T10:00:00+02:00')
            fp.seek(0)
            response = self.client.post(url1, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

            url1 = url + '?timestamp={0}'.format('2017-01-10T10:00:00')
            fp.seek(0)
            response = self.client.post(url1, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @skipIf(USE_WORKER, "Skip if using worker")
    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testReportParsing(self, mock_download_s3):

        url = reverse('streamerreport-list')
        url += '?timestamp={0}'.format('2017-01-10T10:00:00Z')

        test_filename = full_path('valid_100_readings.bin')
        self.s1.input_unit = None
        self.s1.save()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)
        with open(test_filename, 'rb') as fp:
            data = {
                'file': fp,
            }
            mock_download_s3.return_value = fp
            response = self.client.post(url, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            deserialized = json.loads(response.content.decode())
            self.assertEqual(deserialized['count'], 100)
            self.assertEqual(StreamerReport.objects.count(), 1)
            self.assertEqual(StreamData.objects.count(), 101)

            report = StreamerReport.objects.first()
            self.assertTrue(report.successful)
            self.assertEqual(report.original_first_id, 1)  # Normal reports will not have a 0, but this report does
            self.assertEqual(report.original_last_id, 100)
            self.assertEqual(report.actual_first_id, 1)  # 0 is ignored as that should not be legal
            self.assertEqual(report.actual_last_id, 100)
            self.assertEqual(report.num_entries, 100)
            self.assertEqual(str(report.sent_timestamp.isoformat()), '2017-01-10T10:00:00+00:00')
            streamer = report.streamer
            self.assertEqual(streamer.last_id, 100)

            first = StreamData.objects.order_by('stream_slug', 'streamer_local_id', 'timestamp').first()
            self.assertEqual(first.int_value, 0)
            self.assertEqual(first.value, 0.0) # old scheme
            self.assertEqual(first.streamer_local_id, 1)
            self.assertEqual(first.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
            self.assertEqual(first.project_slug, 'p--0000-0002')
            self.assertEqual(first.device_slug, 'd--0000-0000-0000-000a')
            self.assertEqual(first.variable_slug, 'v--0000-0002--5001')
            self.assertEqual(first.device_timestamp, 0)
            self.assertEqual(str(first.timestamp.isoformat()), '2017-01-10T10:00:00+00:00')

            last = StreamData.objects.filter(variable_slug__endswith='5001').last()
            self.assertEqual(last.int_value, 99)
            self.assertEqual(last.value, 99.0) # Old scheme
            self.assertEqual(last.streamer_local_id, 100)
            self.assertEqual(last.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
            self.assertEqual(last.project_slug, 'p--0000-0002')
            self.assertEqual(last.device_slug, 'd--0000-0000-0000-000a')
            self.assertEqual(last.variable_slug, 'v--0000-0002--5001')
            self.assertEqual(last.device_timestamp, 99)
            self.assertEqual(str(last.timestamp.isoformat()), '2017-01-10T10:01:39+00:00')

        StreamerReport.objects.all().delete()
        with open(test_filename, 'rb') as fp:
            data = {
                'file': fp,
            }
            mock_download_s3.return_value = fp
            response = self.client.post(url, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            deserialized = json.loads(response.content.decode())
            self.assertEqual(deserialized['count'], 100)
            self.assertEqual(StreamerReport.objects.count(), 1)
            self.assertEqual(StreamData.objects.count(), 101)

            report = StreamerReport.objects.last()
            self.assertEqual(report.original_first_id, 1)
            self.assertEqual(report.original_last_id, 100)
            self.assertEqual(report.actual_first_id, 0)
            self.assertEqual(report.actual_last_id, 0)
            self.assertEqual(report.num_entries, 0)

        self.client.logout()

    @mock.patch('apps.streamer.worker.common.base_action.ProcessReportBaseAction.schedule')
    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testStreamerReportAPI(self, mock_download_s3, mock_process_report_schedule):

        url = reverse('streamerreport-list')
        url += '?timestamp={0}'.format('2017-01-10T10:00:00Z')

        streamer = self.pd1.streamers.first()
        reports_url = reverse('streamer-report', kwargs={'slug': streamer.slug})

        test_filename = full_path('valid_100_readings.bin')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)
        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp

            data = {
                'file': fp,
            }
            response = self.client.post(url, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            data = {
                'file': fp,
            }
            response = self.client.post(url, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(reports_url+'?staff=1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(len(deserialized), 2)

        self.client.logout()

    @mock.patch('apps.streamer.worker.common.base_action.ProcessReportBaseAction.schedule')
    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testLargeReportUpload(self, mock_download_s3, mock_process_report_schedule):

        url = reverse('streamerreport-list')
        url += '?timestamp={0}'.format('2017-01-10T10:00:00Z')

        test_filename = full_path('valid_10000_readings.bin')

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            ok = self.client.login(email='user1@foo.com', password='pass')
            self.assertTrue(ok)

            data = {
                'file': fp,
            }
            response = self.client.post(url, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            deserialized = json.loads(response.content.decode())
            self.assertEqual(deserialized['count'], 10000)
            self.assertEqual(StreamerReport.objects.count(), 1)

    @skipIf(USE_WORKER, "Skip if using worker")
    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testNewSchemeInputUnits(self, mock_download_s3):

        url = reverse('streamerreport-list')
        url += '?timestamp={0}'.format('2017-02-10T10:00:00Z')

        test_filename = full_path('valid_16_readings.bin')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        with open(test_filename, 'rb') as fp:

            data = {
                'file': fp,
            }
            mock_download_s3.return_value = fp
            response = self.client.post(url, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        data1 = StreamData.objects.first()
        self.assertEqual(data1.int_value, 0)
        # self.assertEqual(data1.value, 0.0)
        data16 = StreamData.objects.filter(variable_slug__endswith='5001').last()
        self.assertEqual(data16.int_value, 15)
        # self.assertEqual(data16.value, 3.0)

