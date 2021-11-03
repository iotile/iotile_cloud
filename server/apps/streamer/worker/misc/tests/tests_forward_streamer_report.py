import json
import os
import dateutil.parser
from unittest import skipIf, mock

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.cache import cache

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin
from apps.stream.models import StreamVariable, StreamId
from apps.streamdata.models import StreamData
from apps.physicaldevice.models import Device
from apps.sensorgraph.models import SensorGraph
from apps.utils.timezone_utils import *
from apps.utils.iotile.streamer import STREAMER_SELECTOR
from apps.utils.dynamic_loading import str_to_class
from apps.configattribute.models import ConfigAttribute
from apps.sqsworker.tests import QueueTestMock
from apps.sqsworker.workerhelper import Worker
from apps.streamer.models import Streamer, StreamerReport

from ...common.test_utils import sqs_process_report_payload

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')

class ReportForwarderTestCase(TestMixin, APITestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.sg1 = SensorGraph.objects.create(
            name='SG 1', report_processing_engine_ver=2, created_by=self.u1, org=self.o1
        )

    def tearDown(self):
        ConfigAttribute.objects.all().delete()
        StreamData.objects.all().delete()
        Streamer.objects.all().delete()
        StreamerReport.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def _full_path(self, filename):
        module_path = os.path.dirname(__file__)
        return os.path.join(module_path, '..', '..', '..', 'data', 'reports', filename)

    @mock.patch('apps.streamer.worker.misc.forward_streamer_report._upload_streamer_report_to_cloud')
    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    @mock.patch('apps.streamer.worker.misc.forward_streamer_report.download_file_from_s3')
    def test_report_forwarder_bin1(self, mock_download_s3_1, mock_download_s3_2, mock_upload):
        device = Device.objects.create_device(
            id=0x235, project=self.p1, label='d1', sg=self.sg1,
            template=self.dt1, created_by=self.u2
        )
        Streamer.objects.create(
            device=device, index=0, created_by=self.u2, selector=0xd7ff, process_engine_ver=2
        )

        url = reverse('streamerreport-list')
        url += '?timestamp={0}'.format('2016-09-28T10:00:00Z')

        test_filename = self._full_path('new_combined_selector.bin')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        ConfigAttribute.objects.get_or_create_attribute(
            target=self.o2,
            name=':classic:streamer:forwarder:config',
            data={
                "enabled": True,
                "api_url": "https://arch.archfx.io",
                "api_key": "foo.bar1",
            },
            updated_by=self.u1
        )
        cache.delete(':classic:streamer:forwarder:config::{}'.format(self.o2.slug))

        with open(test_filename, 'rb') as fp:
            mock_download_s3_1.return_value = fp
            mock_download_s3_2.return_value = fp
            mock_upload.return_value = None
            self.assertEqual(mock_upload.call_count, 0)
            response = self.client.post(url, {'file': fp}, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 1)
            self.assertEqual(mock_upload.call_count, 1)

        self.client.logout()

    @mock.patch('apps.streamer.worker.misc.forward_streamer_report._upload_streamer_report_to_cloud')
    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    @mock.patch('apps.streamer.worker.misc.forward_streamer_report.download_file_from_s3')
    def test_report_forwarder_bin2(self, mock_download_s3_1, mock_download_s3_2, mock_upload):
        """This is a test that can be locally modified to easily upload real data to an ArchFx Cloud
        Just remove the mock_upload, and edit the API Key (but make sure not to commit)
        """
        device = Device.objects.create_device(
            id=0xade, project=self.p1, label='d1', sg=self.sg1,
            template=self.dt1, created_by=self.u2
        )
        Streamer.objects.create(
            device=device, index=255, created_by=self.u2, selector=65535, process_engine_ver=2
        )

        url = reverse('streamerreport-list')
        url += '?timestamp={0}'.format('2016-09-28T10:00:00Z')

        test_filename = self._full_path('device-0ade-report.bin')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        ConfigAttribute.objects.get_or_create_attribute(
            target=self.o2,
            name=':classic:streamer:forwarder:config',
            data={
                "enabled": True,
                "api_url": "https://arch.archfx.io",
                "api_key": "foo.bar",
            },
            updated_by=self.u1
        )
        cache.delete(':classic:streamer:forwarder:config::{}'.format(self.o2.slug))

        with open(test_filename, 'rb') as fp:
            mock_download_s3_1.return_value = fp
            mock_download_s3_2.return_value = fp
            mock_upload.return_value = None
            self.assertEqual(mock_upload.call_count, 0)
            response = self.client.post(url, {'file': fp}, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 1)
            self.assertEqual(mock_upload.call_count, 1)

        self.client.logout()

    @mock.patch('apps.streamer.worker.misc.forward_streamer_report._upload_streamer_report_to_cloud')
    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    @mock.patch('apps.streamer.worker.misc.forward_streamer_report.download_file_from_s3')
    def test_report_forwarder_json(self, mock_download_s3_1, mock_download_s3_2, mock_upload):

        pd1 = Device.objects.create_device(
            id=0xa, project=self.p1, sg=self.sg1, label='d1',
            template=self.dt1, created_by=self.u2
        )
        streamer = Streamer.objects.create(
            device=pd1, process_engine_ver=2, index=100,
            selector=STREAMER_SELECTOR['VIRTUAL1'], created_by=self.u2
        )

        ConfigAttribute.objects.get_or_create_attribute(
            target=self.o2,
            name=':classic:streamer:forwarder:config',
            data={
                "enabled": True,
                "api_url": "https://arch.archfx.io",
                "api_key": "foo.bar2",
            },
            updated_by=self.u1
        )
        cache.delete(':classic:streamer:forwarder:config::{}'.format(self.o2.slug))

        if getattr(settings, 'USE_POSTGRES'):
            user_report = self._full_path('v2_report1.json')
            report = StreamerReport.objects.create(
                streamer=streamer,
                sent_timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                created_by=self.u2
            )

            queue = QueueTestMock()
            msg = sqs_process_report_payload(
                report.get_dropbox_s3_bucket_and_key(ext='.json')[1], 'v2', ext='.json'
            )
            queue.add_messages([
                msg
            ])

            self.assertEqual(mock_upload.call_count, 0)

            with open(user_report, 'rb') as fp:
                mock_download_s3_1.return_value = fp
                mock_download_s3_2.return_value = fp
                mock_upload.return_value = None
                worker = Worker(queue, 2)
                worker.run_once_without_delete()

            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 1)
            self.assertEqual(mock_upload.call_count, 1)

    @mock.patch('apps.streamer.worker.misc.forward_streamer_report._upload_streamer_report_to_cloud')
    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    @mock.patch('apps.streamer.worker.misc.forward_streamer_report.download_file_from_s3')
    def test_report_forwarder_mp(self, mock_download_s3_1, mock_download_s3_2, mock_upload):

        device = Device.objects.create_device(
            id=0x0bd8, project=self.p1, sg=self.sg1, label='d1',
            template=self.dt1, created_by=self.u2
        )
        stremaer = Streamer.objects.create(
            device=device, index=255, created_by=self.u2, selector=65535, process_engine_ver=2
        )

        ConfigAttribute.objects.get_or_create_attribute(
            target=self.o2,
            name=':classic:streamer:forwarder:config',
            data={
                "enabled": True,
                "api_url": "https://arch.archfx.io",
                "api_key": "foo.bar",
            },
            updated_by=self.u1
        )
        cache.delete(':classic:streamer:forwarder:config::{}'.format(self.o2.slug))

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        url = reverse('streamerreport-list')
        url += '?timestamp={0}'.format('2019-11-19T15:17:21Z')

        test_filename = self._full_path('device-0bd8-report.mp')

        with open(test_filename, 'rb') as fp:
            mock_download_s3_1.return_value = fp
            mock_download_s3_2.return_value = fp
            mock_upload.return_value = None
            self.assertEqual(mock_upload.call_count, 0)
            response = self.client.post(url, {'file': fp}, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            deserialized = json.loads(response.content.decode())
            self.assertEqual(deserialized['count'], 28)
            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 1)
            self.assertEqual(mock_upload.call_count, 1)

        self.client.logout()
