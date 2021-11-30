import datetime
import os
import uuid
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.utils.dateparse import parse_datetime

from apps.physicaldevice.models import Device
from apps.sqsworker.dynamodb import DynamoWorkerLogModel, create_worker_log_table_if_needed
from apps.sqsworker.exceptions import *
from apps.sqsworker.tests import QueueTestMock
from apps.sqsworker.workerhelper import Worker
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.models import StreamData
from apps.streamer.models import Streamer, StreamerReport
from apps.streamer.report.worker.handle_delay import HandleDelayAction
from apps.streamer.report.worker.handle_reboot import HandleRebootAction
from apps.streamer.report.worker.process_report import ProcessReportAction
from apps.utils.gid.convert import formatted_gsid
from apps.utils.iotile.streamer import STREAMER_SELECTOR
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import *


def _full_path(filename):
    module_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    return os.path.join(module_path, 'data', 'reports', filename)


class HandleDelayReportTestCase(TestMixin, TestCase):
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
                                                     index=1,
                                                     created_by=self.u2,
                                                     selector=STREAMER_SELECTOR['USER_NO_REBOOTS'],
                                                     is_system=False)
        self.sys_streamer = Streamer.objects.create(device=self.pd1,
                                                    index=0,
                                                    created_by=self.u2,
                                                    selector=STREAMER_SELECTOR['SYSTEM'],
                                                    is_system=True)
        create_worker_log_table_if_needed()

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

    @mock.patch('apps.streamer.report.worker.handle_reboot.HandleRebootAction.schedule')
    @mock.patch('apps.streamer.report.worker.process_report.HandleDelayAction')
    @mock.patch('apps.streamer.report.worker.process_report.HandleRebootAction')
    @mock.patch('apps.streamer.report.worker.process_report.download_streamer_report_from_s3')
    def testHandleDelay(self, mock_download_s3, mock_handle_reboot, mock_handle_delay, mock_reboot_schedule):
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

        report_1 = StreamerReport.objects.create(streamer=self.user_streamer,
                                                 sent_timestamp=sent_timestamp_1,
                                                 created_by=self.u2,
                                                 device_sent_timestamp=12300,
                                                 incremental_id=23)
        report_2 = StreamerReport.objects.create(streamer=self.sys_streamer,
                                                 sent_timestamp=sent_timestamp_1,
                                                 created_by=self.u2,
                                                 device_sent_timestamp=12300,
                                                 incremental_id=24)
        report_3 = StreamerReport.objects.create(streamer=self.user_streamer,
                                                 sent_timestamp=sent_timestamp_2,
                                                 created_by=self.u2,
                                                 device_sent_timestamp=63300,
                                                 incremental_id=110)
        report_4 = StreamerReport.objects.create(streamer=self.sys_streamer,
                                                 sent_timestamp=sent_timestamp_2,
                                                 created_by=self.u2,
                                                 device_sent_timestamp=63300,
                                                 incremental_id=111)
        # Exceptional data point to avoid triggering HandleDelayAction
        StreamData.objects.create(stream_slug=formatted_gsid(pid=self.p1.formatted_gid, did=self.pd1.formatted_gid, vid='5c00'),
                                  streamer_local_id=0,
                                  device_timestamp=0,
                                  timestamp=base_dt,
                                  int_value=0)
        queue.add_messages([
            {
                "module": "apps.streamer.report.worker.process_report",
                "class": "ProcessReportAction",
                "arguments": {
                    "bucket": "dummy_bucket",
                    "key": "dev/user2/{}/{}.bin".format(sent_timestamp_1.isoformat(), str(report_1.id))
                }
            }
        ])
        with open(user_report, 'rb') as fp:
            mock_download_s3.return_value = fp
            worker.run_once_without_delete()
            mock_download_s3.assert_called_with("dummy_bucket", "dev/user2/{}/{}.bin".format(sent_timestamp_1.isoformat(), str(report_1.id)))

        queue.delete_all()
        queue.add_messages([
            {
                "module": "apps.streamer.report.worker.process_report",
                "class": "ProcessReportAction",
                "arguments": {
                    "bucket": "dummy_bucket",
                    "key": "dev/user2/{}/{}.bin".format(sent_timestamp_1.isoformat(), str(report_2.id))
                }
            }
        ])
        with open(sys_report, 'rb') as fp:
            mock_download_s3.return_value = fp
            worker.run_once_without_delete()
            mock_download_s3.assert_called_with("dummy_bucket", "dev/user2/{}/{}.bin".format(sent_timestamp_1.isoformat(), str(report_2.id)))

        queue.delete_all()
        queue.add_messages([
            {
                "module": "apps.streamer.report.worker.process_report",
                "class": "ProcessReportAction",
                "arguments": {
                    "bucket": "dummy_bucket",
                    "key": "dev/user2/{}/{}.bin".format(sent_timestamp_2.isoformat(), str(report_4.id))
                }
            }
        ])
        with open(sys_reboot_report, 'rb') as fp:
            mock_download_s3.return_value = fp
            mock_handle_reboot.schedule.return_value = None
            device = Device.objects.get(slug=self.pd1.slug)
            last_known_id = device.last_known_id

            worker.run_once_without_delete()
            mock_download_s3.assert_called_with("dummy_bucket", "dev/user2/{}/{}.bin".format(sent_timestamp_2.isoformat(), str(report_4.id)))

            report = StreamerReport.objects.first()
            reboot_args = {
                'device_slug': self.pd1.slug,
                'project_id': str(self.p1.id),
                'block_end_id': 111,
                'block_start_id': last_known_id,
                'reboot_ids': [50, 101]
            }
            mock_handle_reboot.schedule.assert_called_with(args=reboot_args, delay_seconds=300)

            action = HandleRebootAction()
            action.execute(arguments=reboot_args)

            mock_reboot_schedule.assert_called_with(args=reboot_args, delay_seconds=180)

        queue.delete_all()
        queue.add_messages([
            {
                "module": "apps.streamer.report.worker.process_report",
                "class": "ProcessReportAction",
                "arguments": {
                    "bucket": "dummy_bucket",
                    "key": "dev/user2/{}/{}.bin".format(sent_timestamp_2.isoformat(), str(report_3.id))
                }
            }
        ])
        with open(user_reboot_report, 'rb') as fp:
            mock_download_s3.return_value = fp
            mock_handle_delay.schedule.return_value = None
            worker.run_once_without_delete()
            mock_download_s3.assert_called_with("dummy_bucket", "dev/user2/{}/{}.bin".format(sent_timestamp_2.isoformat(), str(report_3.id)))
            delay_args = {
                'device_slug': self.pd1.slug,
                'project_id': str(self.p1.id),
                'start_id': 25,
                'end_id': 109,
                'report_id': str(report_3.id)
            }
            mock_handle_delay.schedule.assert_called_with(args=delay_args, delay_seconds=300)
            action = HandleDelayAction()
            action.execute(arguments=delay_args)

        first = StreamData.objects.filter(device_slug=self.pd1.slug, streamer_local_id__gt=0).order_by('timestamp').first()
        self.assertEqual(first.int_value, 1)
        self.assertEqual(first.value, 1.0)
        self.assertEqual(first.streamer_local_id, 1)
        self.assertEqual(first.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
        self.assertEqual(first.project_slug, 'p--0000-0002')
        self.assertEqual(first.device_slug, 'd--0000-0000-0000-000a')
        self.assertEqual(first.variable_slug, 'v--0000-0002--5001')
        self.assertEqual(first.device_timestamp, 10 * 60)
        self.assertEqual(first.timestamp, base_dt + datetime.timedelta(seconds=first.device_timestamp))

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

        expected_base_dt = sent_timestamp_2 - datetime.timedelta(seconds=7 * 10 * 60 + 5 * 60)
        self.assertEqual(reboot_2.timestamp, expected_base_dt + datetime.timedelta(seconds=reboot_2.device_timestamp))

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
        self.assertEqual(last_known_data.timestamp, base_dt + datetime.timedelta(seconds=last_known_data.device_timestamp))
        self.assertFalse(last_known_data.dirty_ts)

    def testException(self):
        action = HandleDelayAction()

        args_missing_fields = {
            'device_slug': self.pd1.slug,
            'start_id': 1,
            'report_id': 'dummy',
        }

        args_bad_slug = {
            'device_slug': 'not-a-slug',
            'project_id': str(self.p1.id),
            'report_id': 'dummy_id',
            'start_id': 1,
            'end_id': 24
        }

        args_bad_project = {
            'device_slug': self.pd1.slug,
            'project_id': uuid.uuid4(),
            'report_id': 'dummy_id',
            'start_id': 1,
            'end_id': 24
        }

        with self.assertRaises(WorkerActionHardError) as context:
            msg = 'Missing fields in arguments payload. Error comes from task HandleDelayAction, received args: {}'.format(args_missing_fields)
            action.execute(args_missing_fields)
        self.assertEqual(str(context.exception), msg)

        with self.assertRaises(WorkerActionHardError) as context:
            msg = "Device with slug {} not found !".format(args_bad_slug['device_slug'])
            action.execute(args_bad_slug)
        self.assertEqual(str(context.exception), msg)

        with self.assertRaises(WorkerActionHardError) as context:
            msg = "Project with id {} not found !".format(args_bad_project['project_id'])
            action.execute(args_bad_project)
        self.assertEqual(str(context.exception), msg)