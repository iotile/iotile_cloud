import datetime
import os
import uuid
from unittest import mock

from django.test import TestCase
from django.utils.dateparse import parse_datetime
from django.conf import settings
from django.core.cache import cache

from apps.utils.test_util import TestMixin
from apps.stream.models import StreamVariable, StreamId
from apps.streamdata.models import StreamData
from apps.physicaldevice.models import Device
from apps.utils.timezone_utils import *
from apps.streamer.models import Streamer, StreamerReport
from apps.sqsworker.workerhelper import Worker
from apps.sqsworker.tests import QueueTestMock
from apps.sqsworker.dynamodb import create_worker_log_table_if_needed, DynamoWorkerLogModel
from apps.utils.gid.convert import formatted_gsid
from apps.sqsworker.exceptions import *

from ..process_report import ProcessReportV1Action, DELAY_SECONDS
from ..handle_reboot import HandleRebootAction
from ...common.test_utils import *


def _full_path(filename):
    module_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    return os.path.join(module_path, 'data', 'reports', filename)


class HandleRebootTestCase(TestMixin, TestCase):
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
        self.pd1 = Device.objects.create_device(id=0xa, project=self.p1, label='d1', template=self.dt1,
                                                created_by=self.u2)
        self.pd2 = Device.objects.create_device(id=0xb, project=self.p2, label='d2', template=self.dt1,
                                                created_by=self.u3)
        StreamId.objects.create_after_new_device(self.pd1)
        StreamId.objects.create_after_new_device(self.pd2)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()
        self.s2 = StreamId.objects.filter(variable=self.v2).first()
        self.user_streamer = Streamer.objects.create(device=self.pd1,
                                                     process_engine_ver=1,
                                                     index=1,
                                                     created_by=self.u2,
                                                     is_system=False)
        self.sys_streamer = Streamer.objects.create(device=self.pd1,
                                                    process_engine_ver=1,
                                                    index=0,
                                                    created_by=self.u2,
                                                    is_system=True)
        create_worker_log_table_if_needed()
        if cache:
            cache.clear()

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
        DynamoWorkerLogModel.delete_table()

    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testHandleReboot(self, mock_download_s3):
        queue = QueueTestMock()
        worker = Worker(queue, 2)
        # user report has 20 readings, 1 reading each 10 mins
        user_report = _full_path('1_user_common_report.bin')
        # system report has 2 reading 5c01, 10 and 20 min after the last reading of user report
        sys_report = _full_path('2_sys_common_report.bin')
        user_reboot_report = _full_path('3_user_reboot_report.bin')
        sys_reboot_report = _full_path('4_sys_reboot_report.bin')

        base_dt = parse_datetime('2017-01-10T10:00:00+00:00')
        sent_timestamp_1 = base_dt + datetime.timedelta(seconds=20 * 60 * 10 + 5 * 60)
        sent_timestamp_2 = base_dt + datetime.timedelta(seconds=105 * 60 * 10 + 5 * 60)

        # Exceptional data point to avoid triggering HandleDelayAction
        p =StreamData.objects.create(stream_slug=formatted_gsid(pid=self.p1.formatted_gid, did=self.pd1.formatted_gid, vid='5c00'),
                                  streamer_local_id=0,
                                  device_timestamp=0,
                                  timestamp=base_dt,
                                  int_value=0,
                                  status='cln')

        report_1 = StreamerReport.objects.create(streamer=self.user_streamer,
                                                 sent_timestamp=sent_timestamp_1,
                                                 created_by=self.u2,
                                                 device_sent_timestamp=12300,
                                                 incremental_id=23)

        queue.add_messages([
            sqs_process_report_payload(report_1.get_dropbox_s3_bucket_and_key()[1], 'v1')
        ])
        with open(user_report, 'rb') as fp:
            mock_download_s3.return_value = fp
            worker.run_once_without_delete()
            mock_download_s3.assert_called_with("dummy_bucket", report_1.get_dropbox_s3_bucket_and_key()[1])

        report_2 = StreamerReport.objects.create(streamer=self.sys_streamer,
                                                 sent_timestamp=sent_timestamp_1,
                                                 created_by=self.u2,
                                                 device_sent_timestamp=12300,
                                                 incremental_id=24)

        queue.delete_all()
        queue.add_messages([
            sqs_process_report_payload(report_2.get_dropbox_s3_bucket_and_key()[1], 'v1')
        ])
        with open(sys_report, 'rb') as fp:
            mock_download_s3.return_value = fp
            worker.run_once_without_delete()
            mock_download_s3.assert_called_with("dummy_bucket", report_2.get_dropbox_s3_bucket_and_key()[1])

        report_3 = StreamerReport.objects.create(streamer=self.user_streamer,
                                                 sent_timestamp=sent_timestamp_2,
                                                 created_by=self.u2,
                                                 device_sent_timestamp=63300,
                                                 incremental_id=110)

        queue.delete_all()
        queue.add_messages([
            sqs_process_report_payload(report_3.get_dropbox_s3_bucket_and_key()[1], 'v1')
        ])
        with open(user_reboot_report, 'rb') as fp:
            mock_download_s3.return_value = fp
            worker.run_once_without_delete()
            mock_download_s3.assert_called_with("dummy_bucket", report_3.get_dropbox_s3_bucket_and_key()[1])

        report_4 = StreamerReport.objects.create(streamer=self.sys_streamer,
                                                 sent_timestamp=sent_timestamp_2,
                                                 created_by=self.u2,
                                                 device_sent_timestamp=63300,
                                                 incremental_id=111)

        queue.delete_all()
        queue.add_messages([
            sqs_process_report_payload(report_4.get_dropbox_s3_bucket_and_key()[1], 'v1')
        ])
        device = Device.objects.get(slug=self.pd1.slug)
        last_known_id = device.last_known_id
        with open(sys_reboot_report, 'rb') as fp:
            mock_download_s3.return_value = fp
            # mock_handle_reboot.schedule.return_value = None

            worker.run_once_without_delete()
            mock_download_s3.assert_called_with("dummy_bucket", report_4.get_dropbox_s3_bucket_and_key()[1])

            reboot_args = {
                'device_slug': self.pd1.slug,
                'project_id': str(self.p1.id),
                'block_end_id': 111,
                'block_start_id': last_known_id,
                'reboot_ids': [50, 101]
            }
            # mock_handle_reboot.schedule.assert_called_with(args=reboot_args, delay_seconds=DELAY_SECONDS)

        queue.delete_all()
        queue.add_messages([
            {
                "module": "apps.streamer.report.worker.handle_reboot",
                "class": "HandleRebootAction",
                "arguments": reboot_args
            }
        ])

        worker.run_once_without_delete()

        first = StreamData.objects.filter(device_slug=self.pd1.slug, streamer_local_id__gt=0).order_by('timestamp').first()
        self.assertEqual(first.int_value, 1)
        self.assertEqual(first.value, 1.0)
        self.assertEqual(first.streamer_local_id, 1)
        self.assertEqual(first.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
        self.assertEqual(first.project_slug, 'p--0000-0002')
        self.assertEqual(first.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(first.variable_slug, 'v--0000-0002--5001')
        self.assertEqual(first.device_timestamp, 10*60)
        # In production, the sent_timestamp is uploaded as metadata to S3, but in dev
        # we use the s3 key, which is restricted to the hour. In this test, this means the
        # timestamp will be 15min behind
        self.assertEqual(first.timestamp, parse_datetime('2017-01-10T09:45:00+00:00'))
        self.assertFalse(first.dirty_ts)

        reboot_2 = StreamData.objects.filter(device_slug=self.pd1.slug, variable_slug__contains='5c00').order_by('streamer_local_id').last()
        self.assertEqual(reboot_2.streamer_local_id, 101)
        self.assertEqual(reboot_2.stream_slug, 's--0000-0002--0000-0000-0000-000a--5c00')
        self.assertEqual(reboot_2.project_slug, 'p--0000-0002')
        self.assertEqual(reboot_2.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(reboot_2.variable_slug, 'v--0000-0002--5c00')
        self.assertEqual(reboot_2.device_timestamp, 3)
        self.assertFalse(reboot_2.dirty_ts)

        """
        for p in StreamData.objects.all().order_by('streamer_local_id'):
            print('{0}:{1} => {2} ({3})'.format(
                p.variable_slug, p.incremental_id, p.timestamp, p.device_timestamp
            ))
        """

        last_before_reboot_2 = StreamData.objects.get(streamer_local_id=reboot_2.streamer_local_id - 1)
        self.assertEqual(last_before_reboot_2.int_value, 100)
        self.assertEqual(last_before_reboot_2.value, 100.0)
        self.assertEqual(last_before_reboot_2.streamer_local_id, 100)
        self.assertEqual(last_before_reboot_2.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
        self.assertEqual(last_before_reboot_2.project_slug, 'p--0000-0002')
        self.assertEqual(last_before_reboot_2.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(last_before_reboot_2.variable_slug, 'v--0000-0002--5001')
        self.assertEqual(last_before_reboot_2.device_timestamp, 49 * 10 * 60)
        self.assertTrue(last_before_reboot_2.dirty_ts)
        self.assertEqual(last_before_reboot_2.status, 'drt')
        self.assertEqual(last_before_reboot_2.timestamp, reboot_2.timestamp - datetime.timedelta(seconds=reboot_2.device_timestamp))
        self.assertEqual(reboot_2.timestamp, parse_datetime('2017-01-11T01:45:03+00:00'))

        reboot_1 = StreamData.objects.filter(device_slug=self.pd1.slug, variable_slug__contains='5c00', streamer_local_id__gt=0).order_by('streamer_local_id').first()

        self.assertEqual(reboot_1.streamer_local_id, 50)
        self.assertEqual(reboot_1.stream_slug, 's--0000-0002--0000-0000-0000-000a--5c00')
        self.assertEqual(reboot_1.project_slug, 'p--0000-0002')
        self.assertEqual(reboot_1.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(reboot_1.variable_slug, 'v--0000-0002--5c00')
        self.assertEqual(reboot_1.device_timestamp, 3)
        self.assertEqual(reboot_1.timestamp, reboot_2.timestamp - datetime.timedelta(seconds=last_before_reboot_2.device_timestamp))
        self.assertTrue(reboot_1.dirty_ts)
        self.assertEqual(reboot_1.status, 'drt')

        # Trusted previous system report found, data is clean
        last_before_reboot_1 = StreamData.objects.get(streamer_local_id=reboot_1.streamer_local_id-1)
        self.assertEqual(last_before_reboot_1.int_value, 49)
        self.assertEqual(last_before_reboot_1.value, 49.0)
        self.assertEqual(last_before_reboot_1.streamer_local_id, 49)
        self.assertEqual(last_before_reboot_1.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
        self.assertEqual(last_before_reboot_1.project_slug, 'p--0000-0002')
        self.assertEqual(last_before_reboot_1.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(last_before_reboot_1.variable_slug, 'v--0000-0002--5001')
        self.assertEqual(last_before_reboot_1.device_timestamp, 47*10*60)
        self.assertEqual(last_before_reboot_1.timestamp, base_dt + datetime.timedelta(seconds=last_before_reboot_1.device_timestamp))
        self.assertFalse(last_before_reboot_1.dirty_ts)
        self.assertEqual(last_before_reboot_1.status, 'cln')

        # data of the first report is still clean
        # last_known_id is the id of the report
        last_known_data = StreamData.objects.get(streamer_local_id=20)
        self.assertEqual(last_known_data.int_value, 20)
        self.assertEqual(last_known_data.value, 20.0)
        self.assertEqual(last_known_data.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
        self.assertEqual(last_known_data.project_slug, 'p--0000-0002')
        self.assertEqual(last_known_data.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(last_known_data.variable_slug, 'v--0000-0002--5001')
        self.assertEqual(last_known_data.device_timestamp, 20 * 10 * 60)
        # self.assertEqual(last_known_data.timestamp, base_dt + datetime.timedelta(seconds=last_known_data.device_timestamp))
        self.assertEqual(last_known_data.timestamp, parse_datetime('2017-01-10T12:55:00+00:00'))
        self.assertFalse(last_known_data.dirty_ts)

        streamer_data_report_1 = StreamData.objects.get(streamer_local_id=23)
        self.assertEqual(streamer_data_report_1.int_value, 1)
        self.assertEqual(streamer_data_report_1.value, 1.0)
        self.assertEqual(streamer_data_report_1.stream_slug, 's--0000-0002--0000-0000-0000-000a--5a05')
        self.assertEqual(streamer_data_report_1.project_slug, 'p--0000-0002')
        self.assertEqual(streamer_data_report_1.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(streamer_data_report_1.variable_slug, 'v--0000-0002--5a05')
        self.assertEqual(streamer_data_report_1.device_timestamp, 20*60*10 + 5*60)
        self.assertEqual(streamer_data_report_1.timestamp.isoformat(),
                         (sent_timestamp_1 - datetime.timedelta(minutes=25)).isoformat())

        streamer_data_report_2 = StreamData.objects.get(streamer_local_id=24)
        self.assertEqual(streamer_data_report_2.int_value, 0)
        self.assertEqual(streamer_data_report_2.value, 0.0)
        self.assertEqual(streamer_data_report_2.stream_slug, 's--0000-0002--0000-0000-0000-000a--5a05')
        self.assertEqual(streamer_data_report_2.project_slug, 'p--0000-0002')
        self.assertEqual(streamer_data_report_2.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(streamer_data_report_2.variable_slug, 'v--0000-0002--5a05')
        self.assertEqual(streamer_data_report_2.device_timestamp, 20*60*10 + 5*60)
        self.assertEqual(streamer_data_report_2.timestamp.isoformat(),
                         (sent_timestamp_1 - datetime.timedelta(minutes=25)).isoformat())

        streamer_data_report_3 = StreamData.objects.get(streamer_local_id=110)
        self.assertEqual(streamer_data_report_3.int_value, 1)
        self.assertEqual(streamer_data_report_3.value, 1.0)
        self.assertEqual(streamer_data_report_3.stream_slug, 's--0000-0002--0000-0000-0000-000a--5a05')
        self.assertEqual(streamer_data_report_3.project_slug, 'p--0000-0002')
        self.assertEqual(streamer_data_report_3.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(streamer_data_report_3.variable_slug, 'v--0000-0002--5a05')
        self.assertEqual(streamer_data_report_3.device_timestamp, 7*10*60 + 5*60)
        self.assertEqual(streamer_data_report_3.timestamp.isoformat(),
                         (sent_timestamp_2 - datetime.timedelta(minutes=35)).isoformat())
        self.assertEqual(streamer_data_report_3.status, 'cln')

        streamer_data_report_4 = StreamData.objects.get(streamer_local_id=111)
        self.assertEqual(streamer_data_report_4.int_value, 0)
        self.assertEqual(streamer_data_report_4.value, 0.0)
        self.assertEqual(streamer_data_report_4.stream_slug, 's--0000-0002--0000-0000-0000-000a--5a05')
        self.assertEqual(streamer_data_report_4.project_slug, 'p--0000-0002')
        self.assertEqual(streamer_data_report_4.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(streamer_data_report_4.variable_slug, 'v--0000-0002--5a05')
        self.assertEqual(streamer_data_report_4.device_timestamp, 7*10*60 + 5*60)
        self.assertEqual(streamer_data_report_4.timestamp.isoformat(),
                         (sent_timestamp_2 - datetime.timedelta(minutes=35)).isoformat())
        self.assertEqual(streamer_data_report_4.status, 'cln')

        # No longer trying to set status unless processed by reboot
        self.assertEqual(StreamData.objects.filter(device_slug=self.pd1.slug, status='unk').count(), 22)
        self.assertEqual(StreamData.objects.filter(device_slug=self.pd1.slug, status='cln').count(), 39)
        self.assertEqual(StreamData.objects.filter(device_slug=self.pd1.slug, status='drt').count(), 51)

    def testException(self):
        action = HandleRebootAction()

        args_missing_fields = {
            'device_slug': self.pd1.slug,
            'project_id': str(self.p1.id),
            'block_start_id': 24,
            'reboot_ids': [50, 101]
        }

        args_bad_slug = {
            'device_slug': 'not-a-slug',
            'project_id': str(self.p1.id),
            'block_end_id': 23,
            'block_start_id': 24,
            'reboot_ids': [50, 101]
        }

        args_bad_proj = {
            'device_slug': self.pd1.slug,
            'project_id': str(uuid.uuid4()),
            'block_end_id': 23,
            'block_start_id': 24,
            'reboot_ids': [50, 101]
        }

        with self.assertRaises(WorkerActionHardError) as context:
            msg = 'Missing fields in arguments payload. Error comes from task HandleRebootAction, received args: {}'.format(args_missing_fields)
            action.execute(args_missing_fields)
        self.assertEqual(str(context.exception), msg)

        with self.assertRaises(WorkerActionHardError) as context:
            msg = "Device with slug {} not found !".format(args_bad_slug['device_slug'])
            action.execute(args_bad_slug)
        self.assertEqual(str(context.exception), msg)

        with self.assertRaises(WorkerActionHardError) as context:
            msg = "Project with id {} not found !".format(args_bad_proj['project_id'])
            action.execute(args_bad_proj)
        self.assertEqual(str(context.exception), msg)

    def testGetDataPoint(self):
        StreamData.objects.create(stream_slug=formatted_gsid(pid=self.p1.formatted_gid, did=self.pd1.formatted_gid, vid='5c00'),
                                  streamer_local_id=3,
                                  device_timestamp=0,
                                  timestamp=parse_datetime('2017-01-10T10:00:00Z'),
                                  int_value=0)

        StreamData.objects.create(stream_slug=formatted_gsid(pid=self.p1.formatted_gid, did=self.pd1.formatted_gid, vid='5c00'),
                                  device_timestamp=0,
                                  timestamp=parse_datetime('2017-01-10T10:00:00Z'),
                                  int_value=0)

        query = StreamData.objects.filter(streamer_local_id__lt=4, streamer_local_id__gt=0,
                                          variable_slug__contains="5c00", dirty_ts=False)

        self.assertEqual(query.count(), 1)
        data = query.first()
        self.assertEqual(data.streamer_local_id, 3)

    @mock.patch('apps.streamer.worker.v1_bin.handle_reboot.HandleRebootAction.schedule')
    @mock.patch('apps.streamer.worker.v1_bin.process_report.HandleRebootAction')
    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testCheckStreamerDelayRedshift(self, mock_download_s3, mock_handle_reboot, mock_schedule):
        # user report has 20 readings, 1 reading each 10 mins
        user_report = _full_path('1_user_common_report.bin')
        # system report has 2 reading 5c01, 10 and 20 min after the last reading of user report
        sys_report = _full_path('2_sys_common_report.bin')
        user_reboot_report = _full_path('3_user_reboot_report.bin')
        sys_reboot_report = _full_path('4_sys_reboot_report.bin')

        base_dt = parse_datetime('2017-01-10T10:00:00+00:00')
        sent_timestamp_1 = base_dt + datetime.timedelta(seconds=20 * 60 * 10 + 5 * 60)
        sent_timestamp_2 = base_dt + datetime.timedelta(seconds=105 * 60 * 10 + 5 * 60)

        report_1 = StreamerReport.objects.create(streamer=self.user_streamer,
                                                 sent_timestamp=sent_timestamp_1,
                                                 created_by=self.u2,
                                                 device_sent_timestamp=12300,
                                                 incremental_id=23)
        # Exceptional data point to avoid triggering HandleDelayAction
        StreamData.objects.create(stream_slug=formatted_gsid(pid=self.p1.formatted_gid, did=self.pd1.formatted_gid, vid='5c00'),
                                  streamer_local_id=0,
                                  device_timestamp=0,
                                  timestamp=base_dt,
                                  int_value=0)
        process_report_action = ProcessReportV1Action()
        handle_reboot_action = HandleRebootAction()
        with open(user_report, 'rb') as fp:
            mock_download_s3.return_value = fp
            args = {
                "bucket": "dummy_bucket",
                "key": report_1.get_dropbox_s3_bucket_and_key()[1]
            }
            process_report_action.execute(args)

        report_2 = StreamerReport.objects.create(streamer=self.sys_streamer,
                                                 sent_timestamp=sent_timestamp_1,
                                                 created_by=self.u2,
                                                 device_sent_timestamp=12300,
                                                 incremental_id=24)

        with open(sys_report, 'rb') as fp:
            mock_download_s3.return_value = fp
            args = {
                "bucket": "dummy_bucket",
                "key": report_2.get_dropbox_s3_bucket_and_key()[1]
            }
            process_report_action.execute(args)

        report_3 = StreamerReport.objects.create(streamer=self.user_streamer,
                                                 sent_timestamp=sent_timestamp_2,
                                                 created_by=self.u2,
                                                 device_sent_timestamp=63300,
                                                 incremental_id=110)

        with open(user_reboot_report, 'rb') as fp:
            mock_download_s3.return_value = fp
            # mock_stream_data_model.objects.bulk_create.return_value = None
            args = {
                "bucket": "dummy_bucket",
                "key": report_3.get_dropbox_s3_bucket_and_key()[1]
            }
            process_report_action.execute(args)

        report_4 = StreamerReport.objects.create(streamer=self.sys_streamer,
                                                 sent_timestamp=sent_timestamp_2,
                                                 created_by=self.u2,
                                                 device_sent_timestamp=63300,
                                                 incremental_id=111)
        device = Device.objects.get(slug=self.pd1.slug)
        last_known_id = device.last_known_id
        with open(sys_reboot_report, 'rb') as fp:
            mock_download_s3.return_value = fp
            mock_handle_reboot.schedule.return_value = None
            args = {
                "bucket": "dummy_bucket",
                "key": report_4.get_dropbox_s3_bucket_and_key()[1]
            }
            process_report_action.execute(args)

        reboot_args = {
            'device_slug': self.pd1.slug,
            'project_id': str(self.p1.id),
            'block_end_id': 111,
            'block_start_id': last_known_id,
            'reboot_ids': [50, 101]
        }

        # Test check delay
        user_streamer = Streamer.objects.get(index=1, device=self.pd1)
        self.assertEqual(user_streamer.last_id, 109)
        user_streamer.last_id = 111
        user_streamer.save()

        handle_reboot_action.execute(reboot_args)
        mock_schedule.assert_called_with(args=reboot_args, delay_seconds=300)

        user_streamer.last_id = 109
        user_streamer.save()
        mock_schedule.reset_mock()
        handle_reboot_action.execute(reboot_args)
        mock_schedule.assert_not_called()

        first = StreamData.objects.filter(device_slug=self.pd1.slug, streamer_local_id__gt=0).order_by('timestamp').first()
        self.assertEqual(first.int_value, 1)
        self.assertEqual(first.value, 1.0)
        self.assertEqual(first.streamer_local_id, 1)
        self.assertEqual(first.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
        self.assertEqual(first.project_slug, 'p--0000-0002')
        self.assertEqual(first.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(first.variable_slug, 'v--0000-0002--5001')
        self.assertEqual(first.device_timestamp, 10 * 60)
        self.assertEqual(first.timestamp, parse_datetime('2017-01-10T09:45:00+00:00'))

        reboot_2 = StreamData.objects.filter(device_slug=self.pd1.slug, variable_slug__contains='5c00').order_by('streamer_local_id').last()
        self.assertEqual(reboot_2.streamer_local_id, 101)
        self.assertEqual(reboot_2.stream_slug, 's--0000-0002--0000-0000-0000-000a--5c00')
        self.assertEqual(reboot_2.project_slug, 'p--0000-0002')
        self.assertEqual(reboot_2.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(reboot_2.variable_slug, 'v--0000-0002--5c00')
        self.assertEqual(reboot_2.device_timestamp, 3)

        last_before_reboot_2 = StreamData.objects.get(streamer_local_id=reboot_2.streamer_local_id - 1)
        self.assertEqual(last_before_reboot_2.int_value, 100)
        self.assertEqual(last_before_reboot_2.value, 100.0)
        self.assertEqual(last_before_reboot_2.streamer_local_id, 100)
        self.assertEqual(last_before_reboot_2.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
        self.assertEqual(last_before_reboot_2.project_slug, 'p--0000-0002')
        self.assertEqual(last_before_reboot_2.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(last_before_reboot_2.variable_slug, 'v--0000-0002--5001')
        self.assertEqual(last_before_reboot_2.device_timestamp, 49 * 10 * 60)
        self.assertEqual(last_before_reboot_2.timestamp, reboot_2.timestamp - datetime.timedelta(seconds=reboot_2.device_timestamp))
        self.assertTrue(last_before_reboot_2.dirty_ts)

        self.assertEqual(reboot_2.timestamp, parse_datetime('2017-01-11T01:45:03+00:00'))

        reboot_1 = StreamData.objects.filter(device_slug=self.pd1.slug, variable_slug__contains='5c00', streamer_local_id__gt=0).order_by(
            'streamer_local_id').first()

        self.assertEqual(reboot_1.streamer_local_id, 50)
        self.assertEqual(reboot_1.stream_slug, 's--0000-0002--0000-0000-0000-000a--5c00')
        self.assertEqual(reboot_1.project_slug, 'p--0000-0002')
        self.assertEqual(reboot_1.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(reboot_1.variable_slug, 'v--0000-0002--5c00')
        self.assertEqual(reboot_1.device_timestamp, 3)
        self.assertEqual(reboot_1.timestamp, reboot_2.timestamp - datetime.timedelta(seconds=last_before_reboot_2.device_timestamp))
        self.assertTrue(reboot_1.dirty_ts)

        # No clean reboot before this point so it becomes dirty
        last_before_reboot_1 = StreamData.objects.get(streamer_local_id=reboot_1.streamer_local_id - 1)
        self.assertEqual(last_before_reboot_1.int_value, 49)
        self.assertEqual(last_before_reboot_1.value, 49.0)
        self.assertEqual(last_before_reboot_1.streamer_local_id, 49)
        self.assertEqual(last_before_reboot_1.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
        self.assertEqual(last_before_reboot_1.project_slug, 'p--0000-0002')
        self.assertEqual(last_before_reboot_1.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(last_before_reboot_1.variable_slug, 'v--0000-0002--5001')
        self.assertEqual(last_before_reboot_1.device_timestamp, 47 * 10 * 60)
        self.assertEqual(last_before_reboot_1.timestamp, base_dt + datetime.timedelta(seconds=last_before_reboot_1.device_timestamp))
        self.assertFalse(last_before_reboot_1.dirty_ts)

        # data of the first report is still clean
        # last_known_id is the id of the report
        last_known_data = StreamData.objects.get(streamer_local_id=20)
        self.assertEqual(last_known_data.int_value, 20)
        self.assertEqual(last_known_data.value, 20.0)
        self.assertEqual(last_known_data.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
        self.assertEqual(last_known_data.project_slug, 'p--0000-0002')
        self.assertEqual(last_known_data.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(last_known_data.variable_slug, 'v--0000-0002--5001')
        self.assertEqual(last_known_data.device_timestamp, 20 * 10 * 60)
        self.assertEqual(last_known_data.timestamp, parse_datetime('2017-01-10T12:55:00+00:00'))
        self.assertFalse(last_known_data.dirty_ts)

    @mock.patch('apps.streamer.worker.v1_bin.process_report.HandleDelayAction')
    @mock.patch('apps.streamer.worker.v1_bin.handle_reboot.HandleRebootAction.schedule')
    @mock.patch('apps.streamer.worker.v1_bin.process_report.HandleRebootAction')
    @mock.patch('apps.streamer.worker.common.base_action.download_file_from_s3')
    def testCheckStreamerUnorderedReport(self, mock_download_s3, mock_handle_reboot, mock_schedule, mock_handle_delay):
        # user report has 20 readings, 1 reading each 10 mins
        user_report = _full_path('1_user_common_report.bin')
        # system report has 2 reading 5c01, 10 and 20 min after the last reading of user report
        sys_report = _full_path('2_sys_common_report.bin')
        user_reboot_report = _full_path('3_user_reboot_report.bin')
        sys_reboot_report = _full_path('4_sys_reboot_report.bin')

        base_dt = parse_datetime('2017-01-10T10:00:00+00:00')
        sent_timestamp_1 = base_dt + datetime.timedelta(seconds=20 * 60 * 10 + 5 * 60)
        sent_timestamp_2 = base_dt + datetime.timedelta(seconds=105 * 60 * 10 + 5 * 60)

        report_1 = StreamerReport.objects.create(streamer=self.user_streamer,
                                                 sent_timestamp=sent_timestamp_1,
                                                 created_by=self.u2,
                                                 device_sent_timestamp=12300,
                                                 incremental_id=23)
        # Exceptional data point to avoid triggering HandleDelayAction
        StreamData.objects.create(stream_slug=formatted_gsid(pid=self.p1.formatted_gid, did=self.pd1.formatted_gid, vid='5c00'),
                                  streamer_local_id=0,
                                  device_timestamp=0,
                                  timestamp=base_dt,
                                  int_value=0)
        process_report_action = ProcessReportV1Action()
        handle_reboot_action = HandleRebootAction()
        with open(user_report, 'rb') as fp:
            mock_download_s3.return_value = fp
            args = {
                "bucket": "dummy_bucket",
                "key": report_1.get_dropbox_s3_bucket_and_key()[1]
            }
            process_report_action.execute(args)

        report_2 = StreamerReport.objects.create(streamer=self.sys_streamer,
                                                 sent_timestamp=sent_timestamp_1,
                                                 created_by=self.u2,
                                                 device_sent_timestamp=12300,
                                                 incremental_id=24)

        with open(sys_report, 'rb') as fp:
            mock_download_s3.return_value = fp
            args = {
                "bucket": "dummy_bucket",
                "key": report_2.get_dropbox_s3_bucket_and_key()[1]
            }
            process_report_action.execute(args)

        device = Device.objects.get(slug=self.pd1.slug)
        last_known_id = device.last_known_id

        report_4 = StreamerReport.objects.create(streamer=self.sys_streamer,
                                                 sent_timestamp=sent_timestamp_2,
                                                 created_by=self.u2,
                                                 device_sent_timestamp=63300,
                                                 incremental_id=111)
        with open(sys_reboot_report, 'rb') as fp:
            mock_download_s3.return_value = fp
            mock_handle_reboot.schedule.return_value = None
            args = {
                "bucket": "dummy_bucket",
                "key": report_4.get_dropbox_s3_bucket_and_key()[1]
            }
            process_report_action.execute(args)

        reboot_args = {
            'device_slug': self.pd1.slug,
            'project_id': str(self.p1.id),
            'block_end_id': 111,
            'block_start_id': last_known_id,
            'reboot_ids': [50, 101]
        }

        # Test check delay
        user_streamer = Streamer.objects.get(index=1, device=self.pd1)
        self.assertEqual(user_streamer.last_id, 20)

        handle_reboot_action.execute(reboot_args)
        # Reschedule due to late user report
        mock_schedule.assert_called_with(args=reboot_args, delay_seconds=300)

        report_3 = StreamerReport.objects.create(streamer=self.user_streamer,
                                                 sent_timestamp=sent_timestamp_2,
                                                 created_by=self.u2,
                                                 device_sent_timestamp=63300,
                                                 incremental_id=110)
        with open(user_reboot_report, 'rb') as fp:
            mock_download_s3.return_value = fp
            # mock_stream_data_model.objects.bulk_create.return_value = None
            args = {
                "bucket": "dummy_bucket",
                "key": report_3.get_dropbox_s3_bucket_and_key()[1]
            }
            process_report_action.execute(args)

        mock_schedule.reset_mock()
        handle_reboot_action.execute(reboot_args)
        mock_schedule.assert_not_called()

        first = StreamData.objects.filter(device_slug=self.pd1.slug, streamer_local_id__gt=0).order_by('timestamp').first()
        self.assertEqual(first.int_value, 1)
        self.assertEqual(first.value, 1.0)
        self.assertEqual(first.streamer_local_id, 1)
        self.assertEqual(first.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
        self.assertEqual(first.project_slug, 'p--0000-0002')
        self.assertEqual(first.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(first.variable_slug, 'v--0000-0002--5001')
        self.assertEqual(first.device_timestamp, 10 * 60)
        self.assertEqual(first.timestamp, parse_datetime('2017-01-10T09:45:00+00:00'))

        reboot_2 = StreamData.objects.filter(device_slug=self.pd1.slug, variable_slug__contains='5c00').order_by('streamer_local_id').last()
        self.assertEqual(reboot_2.streamer_local_id, 101)
        self.assertEqual(reboot_2.stream_slug, 's--0000-0002--0000-0000-0000-000a--5c00')
        self.assertEqual(reboot_2.project_slug, 'p--0000-0002')
        self.assertEqual(reboot_2.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(reboot_2.variable_slug, 'v--0000-0002--5c00')
        self.assertEqual(reboot_2.device_timestamp, 3)

        last_before_reboot_2 = StreamData.objects.get(streamer_local_id=reboot_2.streamer_local_id - 1)
        self.assertEqual(last_before_reboot_2.int_value, 100)
        self.assertEqual(last_before_reboot_2.value, 100.0)
        self.assertEqual(last_before_reboot_2.streamer_local_id, 100)
        self.assertEqual(last_before_reboot_2.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
        self.assertEqual(last_before_reboot_2.project_slug, 'p--0000-0002')
        self.assertEqual(last_before_reboot_2.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(last_before_reboot_2.variable_slug, 'v--0000-0002--5001')
        self.assertEqual(last_before_reboot_2.device_timestamp, 49 * 10 * 60)
        self.assertEqual(last_before_reboot_2.timestamp, reboot_2.timestamp - datetime.timedelta(seconds=reboot_2.device_timestamp))
        self.assertTrue(last_before_reboot_2.dirty_ts)

        self.assertEqual(reboot_2.timestamp, parse_datetime('2017-01-11T01:45:03+00:00'))

        reboot_1 = StreamData.objects.filter(device_slug=self.pd1.slug, variable_slug__contains='5c00', streamer_local_id__gt=0).order_by(
            'streamer_local_id').first()

        self.assertEqual(reboot_1.streamer_local_id, 50)
        self.assertEqual(reboot_1.stream_slug, 's--0000-0002--0000-0000-0000-000a--5c00')
        self.assertEqual(reboot_1.project_slug, 'p--0000-0002')
        self.assertEqual(reboot_1.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(reboot_1.variable_slug, 'v--0000-0002--5c00')
        self.assertEqual(reboot_1.device_timestamp, 3)
        self.assertEqual(reboot_1.timestamp, reboot_2.timestamp - datetime.timedelta(seconds=last_before_reboot_2.device_timestamp))
        self.assertTrue(reboot_1.dirty_ts)

        # No clean reboot before this point so it becomes dirty
        last_before_reboot_1 = StreamData.objects.get(streamer_local_id=reboot_1.streamer_local_id - 1)
        self.assertEqual(last_before_reboot_1.int_value, 49)
        self.assertEqual(last_before_reboot_1.value, 49.0)
        self.assertEqual(last_before_reboot_1.streamer_local_id, 49)
        self.assertEqual(last_before_reboot_1.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
        self.assertEqual(last_before_reboot_1.project_slug, 'p--0000-0002')
        self.assertEqual(last_before_reboot_1.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(last_before_reboot_1.variable_slug, 'v--0000-0002--5001')
        self.assertEqual(last_before_reboot_1.device_timestamp, 47 * 10 * 60)
        self.assertEqual(last_before_reboot_1.timestamp, base_dt + datetime.timedelta(seconds=last_before_reboot_1.device_timestamp))
        self.assertFalse(last_before_reboot_1.dirty_ts)

        # data of the first report is still clean
        # last_known_id is the id of the report
        last_known_data = StreamData.objects.get(streamer_local_id=20)
        self.assertEqual(last_known_data.int_value, 20)
        self.assertEqual(last_known_data.value, 20.0)
        self.assertEqual(last_known_data.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
        self.assertEqual(last_known_data.project_slug, 'p--0000-0002')
        self.assertEqual(last_known_data.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(last_known_data.variable_slug, 'v--0000-0002--5001')
        self.assertEqual(last_known_data.device_timestamp, 20 * 10 * 60)
        self.assertEqual(last_known_data.timestamp, parse_datetime('2017-01-10T12:55:00+00:00'))
        self.assertFalse(last_known_data.dirty_ts)
