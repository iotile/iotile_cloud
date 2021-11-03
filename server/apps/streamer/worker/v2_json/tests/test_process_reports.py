import json
import os
import dateutil.parser
from unittest import skipIf, mock

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils.dateparse import parse_datetime

from apps.utils.test_util import TestMixin
from apps.streamdata.models import StreamData
from apps.streamdata.helpers import StreamDataBuilderHelper
from apps.streamevent.models import StreamEventData
from apps.stream.models import StreamVariable, StreamId
from apps.physicaldevice.models import Device
from apps.utils.timezone_utils import *
from apps.streamer.models import *
from apps.streamer.serializers import *
from apps.sqsworker.workerhelper import Worker
from apps.sqsworker.tests import QueueTestMock
from apps.utils.iotile.streamer import STREAMER_SELECTOR
from apps.sensorgraph.models import SensorGraph

from ..process_report import ProcessReportV2JsonAction

from ...common.test_utils import *

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')

class StreamerV2JsonProcessReportTestCase(TestMixin, TestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=0x5020,
        )
        self.sg = SensorGraph.objects.create_graph(name='SG1', report_processing_engine_ver=100,
                                                   created_by=self.u2, org=self.o1)
        self.pd1 = Device.objects.create_device(id=0xa, project=self.p1, sg=self.sg, label='d1',
                                                template=self.dt1, created_by=self.u2)
        StreamId.objects.create_after_new_device(self.pd1)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()

    def tearDown(self):
        StreamData.objects.all().delete()
        StreamEventData.objects.all().delete()
        Streamer.objects.all().delete()
        StreamerReport.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testBasicJsonFileProcessing(self, mock_download_s3):
        Streamer.objects.all().delete()
        streamer = Streamer.objects.create(device=self.pd1, process_engine_ver=2, index=100,
                                           selector=STREAMER_SELECTOR['VIRTUAL1'],
                                           created_by=self.u2)

        if getattr(settings, 'USE_POSTGRES'):
            user_report = full_path('v2_report1.json')
            report = StreamerReport.objects.create(streamer=streamer,
                                                   sent_timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                                                   created_by=self.u2)

            queue = QueueTestMock()
            msg = sqs_process_report_payload(report.get_dropbox_s3_bucket_and_key(ext='.json')[1], 'v2', ext='.json')
            queue.add_messages([
                msg
            ])

            with open(user_report, 'rb') as fp:
                mock_download_s3.return_value = fp
                worker = Worker(queue, 2)
                worker.run_once_without_delete()
                mock_download_s3.assert_called_with("dummy_bucket", report.get_dropbox_s3_bucket_and_key(ext='.json')[1])

            self.assertEqual(StreamEventData.objects.count(), 2)

            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 1)

            streamer = Streamer.objects.first()
            streamer_report = StreamerReport.objects.first()

            self.assertEqual(streamer_report.streamer.id, streamer.id)
            self.assertEqual(streamer_report.original_first_id, 2)
            self.assertEqual(streamer_report.original_last_id, 3)
            self.assertEqual(streamer_report.actual_first_id, 2)
            self.assertEqual(streamer_report.actual_last_id, 3)
            self.assertEqual(streamer.last_id, 3)

            # Upload same report again to confirm it is not processed
            report = StreamerReport.objects.create(streamer=streamer,
                                                   sent_timestamp=parse_datetime("2017-01-10T10:10:00Z"),
                                                   created_by=self.u2)

            queue = QueueTestMock()
            queue.add_messages([
                sqs_process_report_payload(report.get_dropbox_s3_bucket_and_key(ext='.json')[1], 'v2', ext='.json')
            ])
            with open(user_report, 'rb') as fp:
                mock_download_s3.return_value = fp
                worker = Worker(queue, 2)
                worker.run_once_without_delete()
                mock_download_s3.assert_called_with("dummy_bucket", report.get_dropbox_s3_bucket_and_key(ext='.json')[1])

            self.assertEqual(StreamEventData.objects.count(), 2)

            self.assertEqual(StreamerReport.objects.count(), 2)
            streamer_report = StreamerReport.objects.get(id=report.id)
            self.assertEqual(streamer_report.streamer.id, streamer.id)
            self.assertEqual(streamer_report.original_first_id, 2)
            self.assertEqual(streamer_report.original_last_id, 3)
            self.assertEqual(streamer_report.actual_first_id, 0)
            self.assertEqual(streamer_report.actual_last_id, 0)
            self.assertEqual(streamer.last_id, 3)

    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testBasicMessagePackFileProcessing(self, mock_download_s3):
        Streamer.objects.all().delete()
        streamer = Streamer.objects.create(device=self.pd1, process_engine_ver=2, index=100,
                                           selector=STREAMER_SELECTOR['VIRTUAL1'],
                                           created_by=self.u2)

        if getattr(settings, 'USE_POSTGRES'):
            user_report = full_path('v2_report1.mp')
            report = StreamerReport.objects.create(streamer=streamer,
                                                   sent_timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                                                   created_by=self.u2)

            queue = QueueTestMock()
            queue.add_messages([
                sqs_process_report_payload(report.get_dropbox_s3_bucket_and_key(ext='.mp')[1], 'v2', ext='.json')
            ])

            with open(user_report, 'rb') as fp:
                mock_download_s3.return_value = fp
                worker = Worker(queue, 2)
                worker.run_once_without_delete()
                mock_download_s3.assert_called_with("dummy_bucket", report.get_dropbox_s3_bucket_and_key(ext='.mp')[1])

            self.assertEqual(StreamEventData.objects.count(), 2)

            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 1)

            streamer = Streamer.objects.first()
            streamer_report = StreamerReport.objects.first()

            self.assertEqual(streamer_report.streamer.id, streamer.id)
            self.assertEqual(streamer_report.original_first_id, 2)
            self.assertEqual(streamer_report.original_last_id, 3)
            self.assertEqual(streamer_report.actual_first_id, 2)
            self.assertEqual(streamer_report.actual_last_id, 3)
            self.assertEqual(streamer.last_id, 3)

    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testPython2MessagePackFileProcessing(self, mock_download_s3):
        Streamer.objects.all().delete()
        streamer = Streamer.objects.create(device=self.pd1, process_engine_ver=2, index=100,
                                           selector=STREAMER_SELECTOR['VIRTUAL1'],
                                           created_by=self.u2)

        if getattr(settings, 'USE_POSTGRES'):
            # this msgpack file was created by using Python 2
            user_report = full_path('v2_report1_python2.mp')
            report = StreamerReport.objects.create(streamer=streamer,
                                                   sent_timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                                                   created_by=self.u2)

            queue = QueueTestMock()
            queue.add_messages([
                sqs_process_report_payload(report.get_dropbox_s3_bucket_and_key(ext='.mp')[1], 'v2', ext='.json')
            ])

            with open(user_report, 'rb') as fp:
                mock_download_s3.return_value = fp
                worker = Worker(queue, 2)
                worker.run_once_without_delete()
                mock_download_s3.assert_called_with("dummy_bucket", report.get_dropbox_s3_bucket_and_key(ext='.mp')[1])

            self.assertEqual(StreamEventData.objects.count(), 2)

            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 1)

            streamer = Streamer.objects.first()
            streamer_report = StreamerReport.objects.first()

            self.assertEqual(streamer_report.streamer.id, streamer.id)
            self.assertEqual(streamer_report.original_first_id, 2)
            self.assertEqual(streamer_report.original_last_id, 3)
            self.assertEqual(streamer_report.actual_first_id, 2)
            self.assertEqual(streamer_report.actual_last_id, 3)
            self.assertEqual(streamer.last_id, 3)

    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    @mock.patch('apps.streamevent.helpers.upload_json_data_from_object')
    def testMobileAppMessagePackFileProcessing(self, mock_upload_json, mock_download_s3):
        mock_download_s3.return_value = True
        Streamer.objects.all().delete()
        # change slug of device to match the one from the file
        self.pd1.slug = 'd--0000-0000-0000-0801'
        self.pd1.save()
        streamer = Streamer.objects.create(device=self.pd1, process_engine_ver=2, index=256,
                                           selector=65535,
                                           created_by=self.u2)

        if getattr(settings, 'USE_POSTGRES'):
            # this msgpack file was created by using the mobile app
            user_report = full_path('v2_report_mobile_app.mp')
            report = StreamerReport.objects.create(streamer=streamer,
                                                   sent_timestamp=parse_datetime("2018-11-07T21:50:58.079000Z"),
                                                   created_by=self.u2)

            queue = QueueTestMock()
            queue.add_messages([
                sqs_process_report_payload(report.get_dropbox_s3_bucket_and_key(ext='.mp')[1], 'v2', ext='.json')
            ])

            with open(user_report, 'rb') as fp:
                mock_download_s3.return_value = fp
                worker = Worker(queue, 2)
                worker.run_once_without_delete()
                mock_download_s3.assert_called_with("dummy_bucket", report.get_dropbox_s3_bucket_and_key(ext='.mp')[1])

            self.assertEqual(StreamEventData.objects.count(), 16)

            sed1 = StreamEventData.objects.first()
            self.assertEqual(sed1.extra_data['axis'], 'z')
            self.assertAlmostEqual(sed1.extra_data['peak'], 2.646)
            self.assertAlmostEqual(sed1.extra_data['duration'], 174.37499999999997)
            self.assertAlmostEqual(sed1.extra_data['delta_v_x'], -0.5311312285781252)
            self.assertAlmostEqual(sed1.extra_data['delta_v_y'], 0)
            self.assertAlmostEqual(sed1.extra_data['delta_v_z'], -3.144891523921875)

            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 1)

            streamer = Streamer.objects.first()
            streamer_report = StreamerReport.objects.first()

            self.assertEqual(streamer_report.streamer.id, streamer.id)
            self.assertEqual(streamer_report.original_first_id, 196609)
            self.assertEqual(streamer_report.original_last_id, 196624)
            self.assertEqual(streamer_report.actual_first_id, 196609)
            self.assertEqual(streamer_report.actual_last_id, 196624)
            self.assertEqual(streamer.last_id, 196624)

    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    @mock.patch('apps.streamevent.helpers.upload_json_data_from_object')
    def testJsonFileIssue1296(self, mock_upload_json, mock_download_s3):
        mock_upload_json.return_value = True
        Streamer.objects.all().delete()
        streamer = Streamer.objects.create(device=self.pd1, process_engine_ver=2, index=256,
                                           selector=STREAMER_SELECTOR['VIRTUAL1'],
                                           created_by=self.u2)

        if getattr(settings, 'USE_POSTGRES'):
            user_report = full_path('v2_report2.mp')
            report = StreamerReport.objects.create(streamer=streamer,
                                                   sent_timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                                                   created_by=self.u2)

            queue = QueueTestMock()
            msg = sqs_process_report_payload(report.get_dropbox_s3_bucket_and_key(ext='.mp')[1], 'v2', ext='.mp')
            queue.add_messages([
                msg
            ])

            with open(user_report, 'rb') as fp:
                mock_download_s3.return_value = fp
                worker = Worker(queue, 2)
                worker.run_once_without_delete()
                mock_download_s3.assert_called_with("dummy_bucket", report.get_dropbox_s3_bucket_and_key(ext='.mp')[1])

            self.assertEqual(StreamEventData.objects.count(), 2)

            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 1)

            streamer = Streamer.objects.first()
            streamer_report = StreamerReport.objects.first()

            self.assertEqual(streamer_report.streamer.id, streamer.id)
            self.assertEqual(streamer_report.original_first_id, 1179649)
            self.assertEqual(streamer_report.original_last_id, 1179650)
            self.assertEqual(streamer_report.actual_first_id, 1179649)
            self.assertEqual(streamer_report.actual_last_id, 1179650)
            self.assertEqual(streamer.last_id, 1179650)

    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testE2Processing(self, mock_download_s3):
        Streamer.objects.all().delete()
        streamer = Streamer.objects.create(device=self.pd1, process_engine_ver=2, index=100,
                                           selector=STREAMER_SELECTOR['VIRTUAL1'],
                                           created_by=self.u2)

        if getattr(settings, 'USE_POSTGRES'):
            self.s1.data_type = 'E2'
            self.s1.save()

            helper = StreamDataBuilderHelper()

            data_entries = []
            data_entries.append(helper.build_data_obj(
                stream_slug=self.s1.slug,
                device_timestamp=10,
                streamer_local_id=10,
                timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                int_value=1
            ))
            data_entries.append(helper.build_data_obj(
                stream_slug=self.s1.slug,
                device_timestamp=20,
                streamer_local_id=20,
                timestamp=parse_datetime("2017-01-10T10:00:10Z"),
                int_value=2
            ))
            data_entries.append(helper.build_data_obj(
                stream_slug=self.s1.slug,
                device_timestamp=30,
                streamer_local_id=30,
                timestamp=parse_datetime("2017-01-10T10:00:20Z"),
                int_value=3
            ))

            StreamData.objects.bulk_create(data_entries)
            self.assertEqual(StreamData.objects.count(), 3)

            user_report = full_path('v2_report1.json')
            report = StreamerReport.objects.create(streamer=streamer,
                                                   sent_timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                                                   created_by=self.u2)

            queue = QueueTestMock()
            queue.add_messages([
                sqs_process_report_payload(report.get_dropbox_s3_bucket_and_key(ext='.json')[1], 'v2', ext='.json')
            ])

            with open(user_report, 'rb') as fp:
                mock_download_s3.return_value = fp
                worker = Worker(queue, 2)
                worker.run_once_without_delete()
                mock_download_s3.assert_called_with("dummy_bucket", report.get_dropbox_s3_bucket_and_key(ext='.json')[1])

            self.assertEqual(StreamEventData.objects.count(), 2)

            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 1)

            streamer = Streamer.objects.first()
            streamer_report = StreamerReport.objects.first()

            self.assertEqual(streamer_report.streamer.id, streamer.id)
            self.assertEqual(streamer_report.original_first_id, 2)
            self.assertEqual(streamer_report.original_last_id, 3)
            self.assertEqual(streamer_report.actual_first_id, 2)
            self.assertEqual(streamer_report.actual_last_id, 3)
            self.assertEqual(streamer.last_id, 3)

            e1 = StreamEventData.objects.first()
            self.assertEqual(e1.timestamp, parse_datetime("2017-01-10T10:00:10Z"))
            e2 = StreamEventData.objects.last()
            self.assertEqual(e2.timestamp, parse_datetime("2017-01-10T10:00:20Z"))

    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    @mock.patch('apps.streamevent.helpers.upload_json_data_from_object')
    def testE2ProcessingWithUTC(self, mock_upload_json, mock_download_s3):
        mock_upload_json.return_value = True
        Streamer.objects.all().delete()
        self.pd1.slug = 'd--0000-0000-0000-053a'
        self.pd1.id = 1338
        self.pd1.save()
        streamer = Streamer.objects.create(device=self.pd1, process_engine_ver=2, index=100,
                                           selector=STREAMER_SELECTOR['VIRTUAL1'],
                                           created_by=self.u2)

        if getattr(settings, 'USE_POSTGRES'):
            self.s1.data_type = 'E2'
            self.s1.slug = 's--0000-0002--0000-0000-0000-053a--5020'
            self.s1.save()

            helper = StreamDataBuilderHelper()

            dt = convert_to_utc(Y2K + datetime.timedelta(weeks=800))
            device_timestamp = int(datetime.timedelta(weeks=800).total_seconds())
            device_timestamp = device_timestamp | (1 << 31)

            data_entries = []
            data_entries.append(helper.build_data_obj(
                stream_slug=self.s1.slug,
                device_timestamp=device_timestamp,
                streamer_local_id=11,
                timestamp=dt,
                int_value=1
            ))
            data_entries.append(helper.build_data_obj(
                stream_slug=self.s1.slug,
                device_timestamp=device_timestamp + 100,
                streamer_local_id=12,
                timestamp=dt + datetime.timedelta(seconds=100),
                int_value=2
            ))
            data_entries.append(helper.build_data_obj(
                stream_slug=self.s1.slug,
                device_timestamp=device_timestamp + 200,
                streamer_local_id=13,
                timestamp=dt + datetime.timedelta(seconds=200),
                int_value=3
            ))

            StreamData.objects.bulk_create(data_entries)
            self.assertEqual(StreamData.objects.count(), 3)

            user_report = full_path('v2_report3.json')
            report = StreamerReport.objects.create(streamer=streamer,
                                                   sent_timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                                                   created_by=self.u2)

            queue = QueueTestMock()
            queue.add_messages([
                sqs_process_report_payload(report.get_dropbox_s3_bucket_and_key(ext='.json')[1], 'v2', ext='.json')
            ])

            with open(user_report, 'rb') as fp:
                mock_download_s3.return_value = fp
                worker = Worker(queue, 2)
                worker.run_once_without_delete()
                mock_download_s3.assert_called_with("dummy_bucket", report.get_dropbox_s3_bucket_and_key(ext='.json')[1])

            self.assertEqual(StreamEventData.objects.count(), 2)

            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 1)

            streamer = Streamer.objects.first()
            streamer_report = StreamerReport.objects.first()

            self.assertEqual(streamer_report.streamer.id, streamer.id)
            self.assertEqual(streamer_report.original_first_id, 2)
            self.assertEqual(streamer_report.original_last_id, 3)
            self.assertEqual(streamer_report.actual_first_id, 2)
            self.assertEqual(streamer_report.actual_last_id, 3)
            self.assertEqual(streamer.last_id, 3)

            e1 = StreamEventData.objects.first()
            self.assertEqual(e1.timestamp, parse_datetime("2015-05-02T00:00:00Z"))
            e2 = StreamEventData.objects.last()
            self.assertEqual(e2.timestamp, parse_datetime("2015-05-02T00:01:40Z"))

    @mock.patch('apps.streamer.worker.v2_json.syncup_e2_data.SyncUpE2DataAction.schedule')
    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testE2DelayProcessing(self, mock_download_s3, mock_schedule):

        Streamer.objects.all().delete()
        streamer = Streamer.objects.create(device=self.pd1, process_engine_ver=2, index=100,
                                           selector=STREAMER_SELECTOR['VIRTUAL1'],
                                           created_by=self.u2)

        if getattr(settings, 'USE_POSTGRES'):
            self.s1.data_type = 'E2'
            self.s1.save()

            helper = StreamDataBuilderHelper()

            data_entries = []
            data_entries.append(helper.build_data_obj(
                stream_slug=self.s1.slug,
                device_timestamp=10,
                streamer_local_id=10,
                timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                int_value=1
            ))
            data_entries.append(helper.build_data_obj(
                stream_slug=self.s1.slug,
                device_timestamp=20,
                streamer_local_id=20,
                timestamp=parse_datetime("2017-01-10T10:00:10Z"),
                int_value=2
            ))

            StreamData.objects.bulk_create(data_entries)
            self.assertEqual(StreamData.objects.count(), 2)

            user_report = full_path('v2_report1.json')
            report = StreamerReport.objects.create(streamer=streamer,
                                                   sent_timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                                                   created_by=self.u2)

            queue = QueueTestMock()
            queue.add_messages([
                sqs_process_report_payload(report.get_dropbox_s3_bucket_and_key(ext='.json')[1], 'v2', ext='.json')
            ])

            with open(user_report, 'rb') as fp:
                mock_download_s3.return_value = fp
                worker = Worker(queue, 2)
                worker.run_once_without_delete()
                mock_download_s3.assert_called_with("dummy_bucket", report.get_dropbox_s3_bucket_and_key(ext='.json')[1])
                args = {
                    'stream_slug': 's--0000-0002--0000-0000-0000-000a--5020',
                    'seq_ids': list([3]),
                    'attempt_count': 5
                }
                mock_schedule.assert_called_with(args=args, delay_seconds=600)

            self.assertEqual(StreamEventData.objects.count(), 2)

            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 1)

            streamer = Streamer.objects.first()
            streamer_report = StreamerReport.objects.first()

            self.assertEqual(streamer_report.streamer.id, streamer.id)
            self.assertEqual(streamer_report.original_first_id, 2)
            self.assertEqual(streamer_report.original_last_id, 3)
            self.assertEqual(streamer_report.actual_first_id, 2)
            self.assertEqual(streamer_report.actual_last_id, 3)
            self.assertEqual(streamer.last_id, 3)

            e1 = StreamEventData.objects.first()
            self.assertEqual(e1.timestamp, parse_datetime("2017-01-10T10:00:10Z"))

    @mock.patch('apps.streamer.worker.v2_json.syncup_e2_data.SyncUpE2DataAction.schedule')
    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testEventWithTimestampProcessing(self, mock_download_s3, mock_schedule):

        Streamer.objects.all().delete()
        streamer = Streamer.objects.create(device=self.pd1, process_engine_ver=2, index=100,
                                           selector=STREAMER_SELECTOR['VIRTUAL1'],
                                           created_by=self.u2)

        if getattr(settings, 'USE_POSTGRES'):
            self.s1.data_type = 'E2'
            self.s1.save()

            helper = StreamDataBuilderHelper()

            data_entries = []
            data_entries.append(helper.build_data_obj(
                stream_slug=self.s1.slug,
                device_timestamp=10,
                streamer_local_id=10,
                timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                int_value=1
            ))
            data_entries.append(helper.build_data_obj(
                stream_slug=self.s1.slug,
                device_timestamp=20,
                streamer_local_id=20,
                timestamp=parse_datetime("2017-01-10T10:00:10Z"),
                int_value=2
            ))

            StreamData.objects.bulk_create(data_entries)
            self.assertEqual(StreamData.objects.count(), 2)

            user_report = full_path('v2_report4.json')
            report = StreamerReport.objects.create(streamer=streamer,
                                                   sent_timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                                                   created_by=self.u2)

            queue = QueueTestMock()
            queue.add_messages([
                sqs_process_report_payload(report.get_dropbox_s3_bucket_and_key(ext='.json')[1], 'v2', ext='.json')
            ])

            with open(user_report, 'rb') as fp:
                mock_download_s3.return_value = fp
                worker = Worker(queue, 2)
                worker.run_once_without_delete()
                mock_download_s3.assert_called_with("dummy_bucket", report.get_dropbox_s3_bucket_and_key(ext='.json')[1])
                args = {
                    'stream_slug': 's--0000-0002--0000-0000-0000-000a--5020',
                    'seq_ids': list([3]),
                    'attempt_count': 5
                }
                mock_schedule.assert_not_called()

            self.assertEqual(StreamEventData.objects.count(), 2)

            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 1)

            streamer = Streamer.objects.first()
            streamer_report = StreamerReport.objects.first()

            self.assertEqual(streamer_report.streamer.id, streamer.id)
            self.assertEqual(streamer_report.original_first_id, 2)
            self.assertEqual(streamer_report.original_last_id, 3)
            self.assertEqual(streamer_report.actual_first_id, 2)
            self.assertEqual(streamer_report.actual_last_id, 3)
            self.assertEqual(streamer.last_id, 3)

            e1 = StreamEventData.objects.first()
            self.assertEqual(e1.timestamp, parse_datetime("2017-01-10T10:00:00Z"))
    
    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testJsonEventWithDataProcessing(self, mock_download_s3):
        Streamer.objects.all().delete()
        streamer = Streamer.objects.create(device=self.pd1, process_engine_ver=2, index=100,
                                            selector=STREAMER_SELECTOR['VIRTUAL1'],
                                            created_by=self.u2)

        if getattr(settings, 'USE_POSTGRES'):
            user_report = full_path('v2_event_with_data.json')
            report = StreamerReport.objects.create(streamer=streamer,
                                                    sent_timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                                                    created_by=self.u2)

            queue = QueueTestMock()
            msg = sqs_process_report_payload(report.get_dropbox_s3_bucket_and_key(ext='.json')[1], 'v2', ext='.json')
            queue.add_messages([
                msg
            ])

            with open(user_report, 'rb') as fp:
                mock_download_s3.return_value = fp
                worker = Worker(queue, 2)
                worker.run_once_without_delete()
                mock_download_s3.assert_called_with("dummy_bucket", report.get_dropbox_s3_bucket_and_key(ext='.json')[1])

            self.assertEqual(StreamEventData.objects.count(), 2)
            self.assertEqual(StreamEventData.objects.first().streamer_local_id, 2)
            self.assertEqual(StreamEventData.objects.last().streamer_local_id, 4)

            self.assertEqual(StreamData.objects.count(), 2)
            first = StreamData.objects.first()
            last = StreamData.objects.last()
            self.assertEqual(first.streamer_local_id, 3)
            self.assertEqual(last.streamer_local_id, 5)
            self.assertEqual(first.int_value, 5)
            self.assertEqual(last.int_value, 6)
            self.assertEqual(first.value, 5.0)
            self.assertEqual(last.value, 6.0)

            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 1)

            streamer = Streamer.objects.first()
            streamer_report = StreamerReport.objects.first()

            self.assertEqual(streamer_report.streamer.id, streamer.id)
            self.assertEqual(streamer_report.original_first_id, 2)
            self.assertEqual(streamer_report.original_last_id, 5)
            self.assertEqual(streamer_report.actual_first_id, 2)
            self.assertEqual(streamer_report.actual_last_id, 5)
            self.assertEqual(streamer.last_id, 5)

    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testArchFxBrokerReport1(self, mock_download_s3):
        Streamer.objects.all().delete()
        streamer = Streamer.objects.create(device=self.pd1, process_engine_ver=2, index=255,
                                           selector=STREAMER_SELECTOR['VIRTUAL1'],
                                           created_by=self.u2)

        if getattr(settings, 'USE_POSTGRES'):
            user_report = full_path('report_broker_combined.json')
            report = StreamerReport.objects.create(streamer=streamer,
                                                   sent_timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                                                   created_by=self.u2)

            queue = QueueTestMock()
            msg = sqs_process_report_payload(report.get_dropbox_s3_bucket_and_key(ext='.json')[1], 'v2', ext='.json')
            queue.add_messages([
                msg
            ])

            with open(user_report, 'rb') as fp:
                mock_download_s3.return_value = fp
                worker = Worker(queue, 2)
                worker.run_once_without_delete()
                mock_download_s3.assert_called_with("dummy_bucket", report.get_dropbox_s3_bucket_and_key(ext='.json')[1])

            self.assertEqual(StreamEventData.objects.count(), 5)
            first = StreamEventData.objects.order_by('streamer_local_id').first()
            last = StreamEventData.objects.order_by('streamer_local_id').last()
            self.assertEqual(first.streamer_local_id, 618914710)
            self.assertEqual(first.timestamp, parse_datetime("2019-08-12T08:58:12Z"))
            self.assertEqual(last.streamer_local_id, 618914750)
            self.assertEqual(last.timestamp, parse_datetime("2019-08-12T09:09:54Z"))

            self.assertEqual(StreamData.objects.count(), 11)
            first = StreamData.objects.order_by('streamer_local_id').first()
            last = StreamData.objects.order_by('streamer_local_id').last()
            self.assertEqual(first.streamer_local_id, 618913800)
            self.assertEqual(first.int_value, 0)
            self.assertEqual(first.value, 0.0)
            self.assertEqual(first.timestamp, parse_datetime("2019-08-12T08:30:00.869999Z"))
            self.assertEqual(last.streamer_local_id, 618915600)
            self.assertEqual(last.int_value, 7)
            self.assertEqual(last.value, 7.0)
            self.assertEqual(last.timestamp, parse_datetime("2019-08-12T09:00:00Z"))

            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 1)

            streamer = Streamer.objects.first()
            streamer_report = StreamerReport.objects.first()

            self.assertEqual(streamer_report.streamer.id, streamer.id)
            self.assertEqual(streamer_report.original_first_id, 618913800)
            self.assertEqual(streamer_report.original_last_id, 618915600)
            self.assertEqual(streamer_report.actual_first_id, 618913800)
            self.assertEqual(streamer_report.actual_last_id, 618915600)
            self.assertEqual(streamer.last_id, 618915600)