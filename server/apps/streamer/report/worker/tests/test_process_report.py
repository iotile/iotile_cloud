import datetime
import os
from unittest import mock

import dateutil.parser

from django.conf import settings
from django.core.cache import cache
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
from apps.streamer.report.parser import ReportParser
from apps.streamer.report.worker.process_report import RETRY_DELAY_SECONDS, ProcessReportAction
from apps.streamfilter.models import State, StateTransition, StreamFilter, StreamFilterAction, StreamFilterTrigger
from apps.utils.gid.convert import formatted_gsid
from apps.utils.iotile.streamer import STREAMER_SELECTOR
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import *


def _full_path(filename):
    module_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    return os.path.join(module_path, 'data', 'reports', filename)


class ProcessReportTestCase(TestMixin, TestCase):
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

        if cache:
            cache.clear()

    def tearDown(self):
        StreamData.objects.all().delete()
        Streamer.objects.all().delete()
        StreamerReport.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        StreamFilter.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()
        DynamoWorkerLogModel.delete_table()

        if cache:
            cache.clear()

    def testGettingLastReboot(self):
        reboot_stream_id = '--'.join(['s', self.p1.formatted_gid, self.pd1.formatted_gid, '5c00' ])
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')

        StreamData.objects.create(
            stream_slug=reboot_stream_id,
            timestamp= t0 + datetime.timedelta(seconds=10),
            int_value=1
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            timestamp= t0 + datetime.timedelta(seconds=20),
            int_value=6
        )

        pr = ProcessReportAction()
        pr.device = self.pd1
        last_reboot = pr._get_last_reboot_data_point()
        # Should be None because the records have no streamer_local_id
        self.assertIsNone(last_reboot)

        r1 = StreamData.objects.create(
            stream_slug=reboot_stream_id,
            device_timestamp = 2,
            timestamp= t0 + datetime.timedelta(seconds=30),
            int_value=1,
            streamer_local_id=1
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            device_timestamp = 12,
            timestamp= t0 + datetime.timedelta(seconds=40),
            int_value=8,
            streamer_local_id = 2
        )

        pr.device = self.pd1
        last_reboot = pr._get_last_reboot_data_point()
        # Should not be None as we now have a proper reboot
        self.assertIsNotNone(last_reboot)
        self.assertEqual(r1.timestamp, last_reboot.timestamp)

        r2 = StreamData.objects.create(
            stream_slug=reboot_stream_id,
            device_timestamp = 2,
            timestamp= t0 + datetime.timedelta(seconds=130),
            int_value=1,
            streamer_local_id=3
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            device_timestamp = 12,
            timestamp= t0 + datetime.timedelta(seconds=140),
            int_value=9,
            streamer_local_id = 4
        )

        pr.device = self.pd1
        last_reboot = pr._get_last_reboot_data_point()
        # Should not be None as we now have a second proper reboot
        self.assertIsNotNone(last_reboot)
        self.assertEqual(r2.timestamp, last_reboot.timestamp)

        pr.device = self.pd2
        last_reboot = pr._get_last_reboot_data_point()
        # Should be None as this is a different device without 5c00
        self.assertIsNone(last_reboot)

    @mock.patch('apps.streamer.report.worker.process_report.download_streamer_report_from_s3')
    def testProcessUserReportTwice(self, mock_download_s3):
        report = StreamerReport.objects.create(streamer=self.sys_streamer,
                                               sent_timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                                               created_by=self.u2)

        queue = QueueTestMock()
        queue.add_messages([
            {
                "module": "apps.streamer.report.worker.process_report",
                "class": "ProcessReportAction",
                "arguments": {
                    "bucket": "dummy_bucket",
                    "key": "dev/user2/2017-01-10T10:00:00Z/{}.bin".format(str(report.id))
                }
            }
        ])
        test_filename = _full_path('valid_100_readings.bin')
        with open(test_filename, 'rb') as fp:
            device = Device.objects.get(slug=self.pd1.slug)
            self.assertEqual(device.last_known_id, 1)

            mock_download_s3.return_value = fp
            worker = Worker(queue, 2)
            worker.run_once_without_delete()
            mock_download_s3.assert_called_with("dummy_bucket", "dev/user2/2017-01-10T10:00:00Z/{}.bin".format(report.id))
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
            self.assertEqual(first.value, 0.0)  # old scheme
            self.assertEqual(first.streamer_local_id, 1)
            self.assertEqual(first.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
            self.assertEqual(first.project_slug, 'p--0000-0002')
            self.assertEqual(first.device_slug, 'd--0000-0000-0000-000a')
            self.assertEqual(first.variable_slug, 'v--0000-0002--5001')
            self.assertEqual(first.device_timestamp, 0)
            self.assertEqual(str(first.timestamp.isoformat()), '2017-01-10T10:00:00+00:00')
            self.assertEqual(first.status, 'unk')

            last = StreamData.objects.filter(variable_slug='v--0000-0002--5001').last()
            self.assertEqual(last.int_value, 99)
            self.assertEqual(last.value, 99.0)  # Old scheme
            self.assertEqual(last.streamer_local_id, 100)
            self.assertEqual(last.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
            self.assertEqual(last.project_slug, 'p--0000-0002')
            self.assertEqual(last.device_slug, 'd--0000-0000-0000-000a')
            self.assertEqual(last.device_timestamp, 99)
            self.assertEqual(str(last.timestamp.isoformat()), '2017-01-10T10:01:39+00:00')
            self.assertEqual(last.status, 'unk')

            streamer_data = StreamData.objects.order_by('stream_slug', 'streamer_local_id', 'timestamp').last()
            self.assertEqual(streamer_data.int_value, 0)
            self.assertEqual(streamer_data.value, 0.0)
            self.assertEqual(streamer_data.streamer_local_id, 0)
            self.assertEqual(streamer_data.stream_slug, 's--0000-0002--0000-0000-0000-000a--5a05')
            self.assertEqual(streamer_data.project_slug, 'p--0000-0002')
            self.assertEqual(streamer_data.device_slug, 'd--0000-0000-0000-000a')
            self.assertEqual(streamer_data.variable_slug, 'v--0000-0002--5a05')
            self.assertEqual(streamer_data.device_timestamp, 0)
            self.assertEqual(str(streamer_data.timestamp.isoformat()), '2017-01-10T10:00:00+00:00')
            self.assertEqual(streamer_data.status, 'unk')


        report_dup = StreamerReport.objects.create(streamer=self.sys_streamer,
                                                   sent_timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                                                   created_by=self.u2)
        queue.delete_all()
        queue.add_messages([
            {
                "module": "apps.streamer.report.worker.process_report",
                "class": "ProcessReportAction",
                "arguments": {
                    "bucket": "dummy_bucket",
                    "key": "dev/user2/2017-01-10T10:00:00Z/{}.bin".format(str(report_dup.id))
                }
            }
        ])
        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            worker = Worker(queue, 2)
            worker.run_once_without_delete()
            self.assertEqual(StreamerReport.objects.count(), 2)
            self.assertEqual(StreamData.objects.count(), 101)

            report = StreamerReport.objects.get(id=report_dup.id)
            self.assertEqual(report.original_first_id, 1)
            self.assertEqual(report.original_last_id, 100)
            self.assertEqual(report.actual_first_id, 0)
            self.assertEqual(report.actual_last_id, 0)
            self.assertEqual(report.status, "Success")
            self.assertEqual(report.num_entries, 0)

    def testProcessReadings(self):
        action = ProcessReportAction()

        disabled_stream = StreamId.objects.filter(variable=self.v1).first()

        self.assertEqual(StreamData.objects.filter(stream_slug=disabled_stream.absolute_slug).count(), 0)
        self.assertEqual(disabled_stream.get_data_count(), 0)

        test_filename = _full_path('valid_100_readings.bin')
        with open(test_filename, 'rb') as fp:
            rp = ReportParser()
            rp.parse_header(fp)
            self.assertEqual(rp.header['fmt'], 1)
            self.assertEqual(rp.header['len_low'], 108)
            self.assertEqual(rp.header['len_high'], 6)
            rp.parse_footer(fp)
            self.assertEqual(rp.footer['lowest_id'], 1)
            self.assertEqual(rp.footer['highest_id'], 100)
            self.assertTrue(rp.check_report_hash(fp))

            rp.parse_readings(fp)
            self.assertEqual(len(rp.data), 100)
            self.assertEqual(rp.data[0]['id'], 1)
            self.assertEqual(rp.data[99]['id'], 100)
            self.assertEqual(rp.data[0]['value'], 0)
            self.assertEqual(rp.data[15]['value'], 15)
            self.assertEqual(rp.data[0]['timestamp'], 0)
            self.assertEqual(rp.data[15]['timestamp'], 15)
            self.assertEqual(rp.length, 1644)

        base_dt = parse_datetime('2017-01-10T10:00:00+00:00')

        action.initialize()
        action.device = self.pd1
        action.streamer = self.user_streamer
        action._read_stream_data(rp, base_dt)
        action._commit_stream_data(parser=rp)

        self.assertEqual(action.count, 100)
        self.assertEqual(StreamData.objects.filter(stream_slug=disabled_stream.absolute_slug).count(), 100)
        self.assertEqual(disabled_stream.get_data_count(), 100)

        disabled_stream.enabled = False
        disabled_stream.save()
        self.assertFalse(disabled_stream.enabled)

        action.initialize()
        action.device = self.pd1
        action.streamer = self.user_streamer
        action._read_stream_data(rp, base_dt)
        action._commit_stream_data(parser=rp)

        self.assertEqual(action.count, 0)
        self.assertEqual(StreamData.objects.filter(stream_slug=disabled_stream.absolute_slug).count(), 100)
        self.assertEqual(disabled_stream.get_data_count(), 100)

    @mock.patch('apps.streamer.report.worker.process_report.HandleRebootAction')
    @mock.patch('apps.streamer.report.worker.process_report.download_streamer_report_from_s3')
    def testProcessReport(self, mock_download_s3, mock_handle_reboot):
        queue = QueueTestMock()
        worker = Worker(queue, 2)
        # user report has 20 readings, 1 reading each 10 mins
        user_report = _full_path('1_user_common_report.bin')

        # system report has 2 reading 5c01, 10 and 20 min after the last reading of user report
        sys_report = _full_path('2_sys_common_report.bin')

        user_reboot_report = _full_path('3_user_reboot_report.bin')

        sys_reboot_report = _full_path('4_sys_reboot_report.bin')

        base_dt = parse_datetime('2017-01-10T10:00:00+00:00')

        sent_timestamp_1 = base_dt + datetime.timedelta(seconds=20*60*10 + 5*60)

        sent_timestamp_2 = base_dt + datetime.timedelta(seconds=105*60*10 + 5*60)

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
            device = Device.objects.get(slug=self.pd1.slug)
            self.assertEqual(device.last_known_id, 1)

            mock_download_s3.return_value = fp
            worker.run_once_without_delete()
            mock_download_s3.assert_called_with("dummy_bucket", "dev/user2/{}/{}.bin".format(sent_timestamp_1.isoformat(), str(report_1.id)))

            report = StreamerReport.objects.get(id=report_1.id)
            self.assertTrue(report.successful)
            self.assertEqual(report.original_first_id, 1)
            self.assertEqual(report.original_last_id, 20)
            self.assertEqual(report.actual_first_id, 1)
            self.assertEqual(report.actual_last_id, 20)
            self.assertEqual(report.num_entries, 20)
            self.assertEqual(str(report.sent_timestamp.isoformat()), sent_timestamp_1.isoformat())
            streamer = report.streamer
            self.assertEqual(streamer.last_id, 20)

            # report is sent 5 min after a the last reading
            device = Device.objects.get(slug=self.pd1.slug)
            self.assertEqual(device.last_known_id, 1)

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

            report = StreamerReport.objects.get(id=report_2.id)
            self.assertTrue(report.successful)
            self.assertEqual(report.original_first_id, 21)
            self.assertEqual(report.original_last_id, 22)
            self.assertEqual(report.actual_first_id, 21)
            self.assertEqual(report.actual_last_id, 22)
            self.assertEqual(report.num_entries, 2)
            self.assertEqual(str(report.sent_timestamp.isoformat()), sent_timestamp_1.isoformat())
            streamer = report.streamer
            self.assertEqual(streamer.last_id, 22)

            device = Device.objects.get(slug=self.pd1.slug)
            # last_known_id is set to the report id
            self.assertEqual(device.last_known_id, 24)

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
            worker.run_once_without_delete()
            mock_download_s3.assert_called_with("dummy_bucket", "dev/user2/{}/{}.bin".format(sent_timestamp_2.isoformat(), str(report_3.id)))

            report = StreamerReport.objects.get(id=report_3.id)
            self.assertTrue(report.successful)
            self.assertEqual(report.original_first_id, 25)
            self.assertEqual(report.original_last_id, 109)
            self.assertEqual(report.actual_first_id, 25)
            self.assertEqual(report.actual_last_id, 109)
            self.assertEqual(report.num_entries, 85)
            self.assertEqual(str(report.sent_timestamp.isoformat()), sent_timestamp_2.isoformat())
            streamer = report.streamer
            self.assertEqual(streamer.last_id, 109)

            device = Device.objects.get(slug=self.pd1.slug)
            # last_known_id is unchanged since this is an user report
            self.assertEqual(device.last_known_id, 24)
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

            device = Device.objects.get(slug=self.pd1.slug)
            report = StreamerReport.objects.get(id=report_4.id)
            self.assertTrue(report.successful)
            self.assertEqual(report.original_first_id, 50)
            self.assertEqual(report.original_last_id, 101)
            self.assertEqual(report.actual_first_id, 50)
            self.assertEqual(report.actual_last_id, 101)
            self.assertEqual(str(report.sent_timestamp.isoformat()), sent_timestamp_2.isoformat())
            streamer = report.streamer
            self.assertEqual(streamer.last_id, 101)
            reboot_args = {
                'device_slug': self.pd1.slug,
                'project_id': str(self.p1.id),
                'block_end_id': 111,
                'block_start_id': last_known_id,
                'reboot_ids': [50, 101]
            }
            mock_handle_reboot.schedule.assert_called_with(args=reboot_args, delay_seconds=RETRY_DELAY_SECONDS)

            # last_known_id is unchanged since this is an user report
            self.assertEqual(device.last_known_id, 111)

    @mock.patch('apps.streamer.report.worker.process_report.download_streamer_report_from_s3')
    def testException(self, mock_download_s3):
        base_dt = parse_datetime('2017-01-10T10:00:00+00:00')
        report = StreamerReport.objects.create(streamer=self.user_streamer,
                                                 sent_timestamp=base_dt,
                                                 created_by=self.u2)

        # Exceptional data point to avoid triggering HandleDelayAction
        StreamData.objects.create(stream_slug=formatted_gsid(pid=self.p1.formatted_gid, did=self.pd1.formatted_gid, vid='5c00'),
                                  streamer_local_id=0,
                                  device_timestamp=0,
                                  timestamp=base_dt,
                                  int_value=0)

        action = ProcessReportAction()
        args_user_not_exist = {
            "bucket": "dummy_bucket",
            "key": "dev/not_user/2017-01-10T10:00:00Z/dummy_key.bin"
        }
        args_bad_timestamp = {
            "bucket": "dummy_bucket",
            "key": "dev/user2/20170110T100000Z/{}.bin".format(str(report.id))
        }
        args_bad_key = {
            "bucket": "dummy_bucket",
            "key": "dev/user2"
        }
        args_missing_fields = {
            "not_bucket": "dummy_bucket",
            "key": "dev/user2/2017-01-10T10:00:00Z/dummy_key.bin"
        }
        args_bad_report_id = {
            "bucket": "dummy_bucket",
            "key": "dev/user2/2017-01-10T10:00:00Z/bac439fd-fa8f-4938-8c3f-5c97b80d6c47.bin"
        }
        args = {
            "bucket": "dummy_bucket",
            "key": "dev/user2/2017-01-10T10:00:00Z/{}.bin".format(str(report.id))
        }

        test_filename = _full_path('valid_100_readings.bin')
        file_not_a_report = _full_path('not_a_report.jpg')
        file_invalid_footer = _full_path('invalid_footer_16_readings.bin')
        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp

            with self.assertRaises(WorkerActionHardError) as context:
                msg = 'User does not exist. Incorrect report in bucket dummy_bucket, key : dev/not_user/2017-01-10T10:00:00Z/dummy_key.bin'
                action.execute(args_user_not_exist)
                mock_download_s3.assert_called_with("dummy_bucket", "dev/not_user/2017-01-10T10:00:00Z/dummy_key.bin")
            self.assertEqual(str(context.exception), msg)

            with self.assertRaises(WorkerActionHardError) as context:
                msg = "Received date time in key is not valid. Incorrect timestamp in bucket dummy_bucket, key : dev/user2/20170110T100000Z/{}.bin".format(str(report.id))
                action.execute(args_bad_timestamp)
                mock_download_s3.assert_called_with("dummy_bucket", "dev/user2/20170110T100000Z/{}.bin".format(str(report.id)))
            self.assertEqual(str(context.exception), msg)

            with self.assertRaises(WorkerActionHardError) as context:
                msg = "Error: list index out of range. Incorrect key format in payload with bucket dummy_bucket, key : dev/user2"
                action.execute(args_bad_key)
                mock_download_s3.assert_called_with("dummy_bucket", "dev/user2")
            self.assertEqual(str(context.exception), msg)

            with self.assertRaises(WorkerActionHardError) as context:
                msg = "Bucket and/or key not found in arguments. Error comes from task: {}".format(args_missing_fields)
                action.execute(args_missing_fields)
                mock_download_s3.assert_not_called()
            self.assertEqual(str(context.exception), msg)

            with self.assertRaises(WorkerActionHardError) as context:
                msg = "Streamer report bac439fd-fa8f-4938-8c3f-5c97b80d6c47.bin not found !"
                action.execute(args_bad_report_id)
                mock_download_s3.assert_called_with("dummy_bucket", "dev/user2/2017-01-10T10:00:00Z/bac439fd-fa8f-4938-8c3f-5c97b80d6c47.bin")
            self.assertEqual(str(context.exception), msg)

            with self.assertRaises(WorkerActionHardError) as context:
                mock_download_s3.side_effect = Exception("Fail to download file from s3")
                msg = "Error: Fail to download file from s3. Incorrect report in bucket dummy_bucket, key : dev/user2/2017-01-10T10:00:00Z/{}.bin".format(str(report.id))
                action.execute(args)
                mock_download_s3.assert_called_with("dummy_bucket", "dev/user2/2017-01-10T10:00:00Z/{}.bin".format(str(report.id)))
            self.assertEqual(str(context.exception), msg)

        mock_download_s3.side_effect = None
        with open(file_not_a_report, 'rb') as fp:
            mock_download_s3.return_value = fp

            with self.assertRaises(WorkerActionHardError) as context:
                msg = 'Unsupported Report Format: 255'
                action.execute(args)
                mock_download_s3.assert_called_with("dummy_bucket", "dev/user2/2017-01-10T10:00:00Z/dummy_key.bin")
            self.assertEqual(str(context.exception), msg)

        with open(file_invalid_footer, 'rb') as fp:
            mock_download_s3.return_value = fp

            with self.assertRaises(WorkerActionHardError) as context:
                msg = 'Invalid Report Hash'
                action.execute(args)
                mock_download_s3.assert_called_with("dummy_bucket", "dev/user2/2017-01-10T10:00:00Z/dummy_key.bin")
            self.assertTrue(msg in str(context.exception))

    @mock.patch('apps.streamer.report.worker.process_report.download_streamer_report_from_s3')
    def testProcessReportWithDeviceFilter(self, mock_download_s3):
        if getattr(settings, 'USE_POSTGRES'):
            user_report = _full_path('1_user_common_report.bin')
            report = StreamerReport.objects.create(streamer=self.user_streamer,
                                                     sent_timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                                                     created_by=self.u2)
            f = StreamFilter.objects.create_filter_from_streamid(
                name='filter 1', input_stream=self.s1, created_by=self.u2
            )
            extra_payload = {
                "notification_recipient": ["org:admin"]
            }
            state1 = State.objects.create(label="state1", filter=f, created_by=self.u2)
            state2 = State.objects.create(label="state2", filter=f, created_by=self.u2)
            a = StreamFilterAction.objects.create(
                type='eml', created_by=self.u2, extra_payload= extra_payload, on='entry', state=state2
            )
            transition = StateTransition.objects.create(src=state1, dst=state2, filter=f, created_by=self.u2)
            t = StreamFilterTrigger.objects.create(operator='ge', created_by=self.u2, filter=f, threshold=10, transition=transition)

            queue = QueueTestMock()
            queue.add_messages([
                {
                    "module": "apps.streamer.report.worker.process_report",
                    "class": "ProcessReportAction",
                    "arguments": {
                        "bucket": "dummy_bucket",
                        "key": "dev/user2/2017-01-10T10:00:00Z/{}.bin".format(str(report.id))
                    }
                }
            ])

            with open(user_report, 'rb') as fp:
                mock_download_s3.return_value = fp
                worker = Worker(queue, 2)
                worker.run_once_without_delete()
                mock_download_s3.assert_called_with("dummy_bucket", "dev/user2/2017-01-10T10:00:00Z/{}.bin".format(report.id))

    @mock.patch('apps.streamer.report.worker.process_report.download_streamer_report_from_s3')
    def testProcessReportWithProjectFilter(self, mock_download_s3):
        if getattr(settings, 'USE_POSTGRES'):
            user_report = _full_path('1_user_common_report.bin')
            report = StreamerReport.objects.create(streamer=self.user_streamer,
                                                   sent_timestamp=parse_datetime("2017-01-10T10:00:00Z"),
                                                   created_by=self.u2)
            f = StreamFilter.objects.create_filter_from_streamid(
                name='filter 1', input_stream=self.s1, created_by=self.u2
            )
            extra_payload = {
                "notification_recipient": ["user:user1"],
                "notification_level": "warn",
                "custom_note": "dummy"
            }
            state1 = State.objects.create(label="state1", filter=f, created_by=self.u2)
            state2 = State.objects.create(label="state2", filter=f, created_by=self.u2)
            a = StreamFilterAction.objects.create(
                type='eml', created_by=self.u2, extra_payload=extra_payload, on='exit', state=state2
            )
            transition = StateTransition.objects.create(src=state1, dst=state2, filter=f, created_by=self.u2)
            t = StreamFilterTrigger.objects.create(operator='ge', created_by=self.u2, filter=f, threshold=10, transition=transition)

            queue = QueueTestMock()
            queue.add_messages([
                {
                    "module": "apps.streamer.report.worker.process_report",
                    "class": "ProcessReportAction",
                    "arguments": {
                        "bucket": "dummy_bucket",
                        "key": "dev/user2/2017-01-10T10:00:00Z/{}.bin".format(str(report.id))
                    }
                }
            ])

            with open(user_report, 'rb') as fp:
                mock_download_s3.return_value = fp
                worker = Worker(queue, 2)
                worker.run_once_without_delete()
                mock_download_s3.assert_called_with("dummy_bucket", "dev/user2/2017-01-10T10:00:00Z/{}.bin".format(report.id))
                data_threshold = StreamData.objects.get(stream_slug=self.s1.slug, int_value=t.threshold)
