# from datetime import timedelta
# from unittest import mock

# import dateutil.parser
# from django.test import TestCase, override_settings

# from apps.physicaldevice.models import Device
# from apps.sqsworker.exceptions import WorkerActionHardError
# from apps.sqsworker.tests import QueueTestMock
# from apps.sqsworker.workerhelper import Worker
# from apps.stream.models import StreamId, StreamVariable
# from apps.streamdata.models import StreamData
# from apps.streamevent.models import StreamEventData
# from apps.streamtimeseries.models import StreamTimeSeriesEvent, StreamTimeSeriesValue
# from apps.streamtimeseries.worker.migrate import MigrateDataAction
# from apps.utils.data_helpers.convert import DataConverter
# from apps.utils.test_util import TestMixin


# class MigrateDataTestCase(TestMixin, TestCase):

#     def _create_stream_data(self):
#         self.sd11 = StreamData.objects.create(
#             stream_slug=self.s1.slug,
#             type='Num',
#             timestamp=self.ts_now + timedelta(seconds=10),
#             int_value=5,
#             streamer_local_id=5,
#         )
#         self.sd12 = StreamData.objects.create(
#             stream_slug=self.s1.slug,
#             type='Num',
#             timestamp=self.ts_now + timedelta(seconds=20),
#             streamer_local_id=6,
#             int_value=6,
#         )
#         self.sd13 = StreamData.objects.create(
#             stream_slug=self.s1.slug,
#             type='Num',
#             timestamp=self.ts_now + timedelta(seconds=30),
#             int_value=7,
#             streamer_local_id=7,
#         )
#         self.sd14 = StreamData.objects.create(
#             stream_slug=self.s1.slug,
#             type='Num',
#             timestamp=self.ts_now + timedelta(seconds=40),
#             int_value=8,
#             streamer_local_id=8,
#         )
#         self.sd15 = StreamData.objects.create(
#             stream_slug=self.s1.slug,
#             type='Num',
#             timestamp=self.ts_now + timedelta(seconds=50),
#             int_value=9,
#             streamer_local_id=9,
#         )
#         self.sd16 = StreamData.objects.create(
#             stream_slug=self.s1.slug,
#             type='Num',
#             timestamp=self.ts_now + timedelta(seconds=60),
#             int_value=10,
#             streamer_local_id=10,
#         )
#         self.sd21 = StreamData.objects.create(
#             stream_slug=self.s2.slug,
#             type='Num',
#             timestamp=self.ts_now + timedelta(seconds=10),
#             int_value=5,
#             streamer_local_id=5,
#         )
#         self.sd22 = StreamData.objects.create(
#             stream_slug=self.s2.slug,
#             type='Num',
#             timestamp=self.ts_now + timedelta(seconds=20),
#             int_value=6,
#             streamer_local_id=6,
#         )
#         self.sd23 = StreamData.objects.create(
#             stream_slug=self.s2.slug,
#             type='Num',
#             timestamp=self.ts_now + timedelta(seconds=30),
#             int_value=7,
#             streamer_local_id=7,
#         )

#     def _create_stream_events(self):
#         self.se11 = StreamEventData.objects.create(
#             stream_slug=self.s1.slug,
#             timestamp=self.ts_now + timedelta(seconds=10),
#             streamer_local_id=5,
#             extra_data={'some_data': 5},
#         )
#         self.se12 = StreamEventData.objects.create(
#             stream_slug=self.s1.slug,
#             timestamp=self.ts_now + timedelta(seconds=20),
#             streamer_local_id=6,
#             extra_data={'some_data': 6},
#         )
#         self.se13 = StreamEventData.objects.create(
#             stream_slug=self.s1.slug,
#             timestamp=self.ts_now + timedelta(seconds=30),
#             streamer_local_id=7,
#             extra_data={'some_data': 7},
#         )
#         self.se14 = StreamEventData.objects.create(
#             stream_slug=self.s1.slug,
#             timestamp=self.ts_now + timedelta(seconds=40),
#             streamer_local_id=8,
#             extra_data={'some_data': 8},
#         )
#         self.se15 = StreamEventData.objects.create(
#             stream_slug=self.s1.slug,
#             timestamp=self.ts_now + timedelta(seconds=50),
#             streamer_local_id=9,
#             extra_data={'some_data': 9},
#         )
#         self.se16 = StreamEventData.objects.create(
#             stream_slug=self.s1.slug,
#             timestamp=self.ts_now + timedelta(seconds=60),
#             streamer_local_id=10,
#             extra_data={'some_data': 10},
#         )
#         self.se21 = StreamEventData.objects.create(
#             stream_slug=self.s2.slug,
#             timestamp=self.ts_now + timedelta(seconds=10),
#             streamer_local_id=5,
#             extra_data={'some_data': 5},
#         )
#         self.se22 = StreamEventData.objects.create(
#             stream_slug=self.s2.slug,
#             timestamp=self.ts_now + timedelta(seconds=20),
#             streamer_local_id=6,
#             extra_data={'some_data': 6},
#         )
#         self.se23 = StreamEventData.objects.create(
#             stream_slug=self.s2.slug,
#             timestamp=self.ts_now + timedelta(seconds=30),
#             streamer_local_id=7,
#             extra_data={'some_data': 7},
#         )

#     def setUp(self):
#         self.usersTestSetup()
#         self.orgTestSetup()
#         self.deviceTemplateTestSetup()
#         self.v1 = StreamVariable.objects.create_variable(
#             name='Var A', project=self.p1, created_by=self.u2, lid=1,
#         )
#         self.v2 = StreamVariable.objects.create_variable(
#             name='Var B', project=self.p2, created_by=self.u3, lid=2,
#         )
#         self.v3 = StreamVariable.objects.create_variable(
#             name='Var C', project=self.p1, created_by=self.u2, lid=3,
#         )
#         self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
#         self.pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)
#         StreamId.objects.create_after_new_device(self.pd1)
#         StreamId.objects.create_after_new_device(self.pd2)
#         self.s1 = StreamId.objects.filter(variable=self.v1).first()
#         self.s2 = StreamId.objects.filter(variable=self.v2).first()
#         self.s3 = StreamId.objects.filter(variable=self.v3).first()

#         self.ts_now = dateutil.parser.parse('2016-09-28T10:00:00Z')

#     def tearDown(self):
#         StreamTimeSeriesEvent.objects.all().delete()
#         StreamTimeSeriesValue.objects.all().delete()
#         StreamEventData.objects.all().delete()
#         StreamData.objects.all().delete()
#         StreamId.objects.all().delete()
#         StreamVariable.objects.all().delete()
#         Device.objects.all().delete()
#         self.deviceTemplateTestTearDown()
#         self.orgTestTearDown()
#         self.userTestTearDown()

#     def testMigrateData(self):
#         self._create_stream_data()

#         queue = QueueTestMock()
#         worker = Worker(queue, 2)

#         self.assertEqual(StreamData.objects.count(), 9)
#         queue.add_messages([
#             {
#                 'module': 'apps.streamtimeseries.worker.migrate',
#                 'class': 'MigrateDataAction',
#                 'arguments': {
#                     'migration_type': 'data',
#                     'stream_slug': self.s1.slug,
#                     'start': 6,
#                     'end': 10,
#                 }
#             }
#         ])
#         worker.run_once_without_delete()
#         self.assertEqual(StreamData.objects.count(), 9)
#         self.assertEqual(StreamTimeSeriesValue.objects.count(), 4)
#         self.assertEqual(StreamTimeSeriesValue.objects.filter(stream_slug=self.s1.slug).count(), 4)
#         stsv = StreamTimeSeriesValue.objects.first()
#         self.assertEqual(stsv.stream_slug, self.s1.slug)
#         self.assertEqual(stsv.type, 'Num')
#         self.assertEqual(stsv.timestamp, self.ts_now + timedelta(seconds=20))
#         self.assertEqual(stsv.device_seqid, 6)
#         self.assertEqual(stsv.raw_value, 6)

#         queue.delete_all()
#         queue.add_messages([
#             {
#                 'module': 'apps.streamtimeseries.worker.migrate',
#                 'class': 'MigrateDataAction',
#                 'arguments': {
#                     'migration_type': 'data',
#                     'stream_slug': self.s2.slug,
#                 }
#             }
#         ])
#         worker.run_once_without_delete()
#         self.assertEqual(StreamData.objects.count(), 9)
#         self.assertEqual(StreamTimeSeriesValue.objects.count(), 7)
#         self.assertEqual(StreamTimeSeriesValue.objects.filter(stream_slug=self.s2.slug).count(), 3)
#         stsv = StreamTimeSeriesValue.objects.filter(stream_slug=self.s2.slug).first()
#         self.assertEqual(stsv.stream_slug, self.s2.slug)
#         self.assertEqual(stsv.type, 'Num')
#         self.assertEqual(stsv.timestamp, self.ts_now + timedelta(seconds=10))
#         self.assertEqual(stsv.device_seqid, 5)
#         self.assertEqual(stsv.raw_value, 5)

#         # if stream_slug doesn't exist
#         queue.delete_all()
#         queue.add_messages([
#             {
#                 'module': 'apps.streamtimeseries.worker.migrate',
#                 'class': 'MigrateDataAction',
#                 'arguments': {
#                     'migration_type': 'data',
#                     'stream_slug': 'doesnotexist',
#                 }
#             }
#         ])
#         worker.run_once_without_delete()
#         # nothing happens
#         self.assertEqual(StreamData.objects.count(), 9)
#         self.assertEqual(StreamTimeSeriesValue.objects.count(), 7)

#         # if start > end
#         queue.delete_all()
#         queue.add_messages([
#             {
#                 'module': 'apps.streamtimeseries.worker.migrate',
#                 'class': 'MigrateDataAction',
#                 'arguments': {
#                     'migration_type': 'data',
#                     'stream_slug': self.s1.slug,
#                     'start': 8,
#                     'end': 7,
#                 }
#             }
#         ])
#         worker.run_once_without_delete()
#         # nothing happens
#         self.assertEqual(StreamData.objects.count(), 9)
#         self.assertEqual(StreamTimeSeriesValue.objects.count(), 7)

#     @mock.patch.object(MigrateDataAction, '_write_stream_batch')
#     @override_settings(USE_FIREHOSE_STREAMTIMESERIES=True)
#     def testMigrateDataUsingFirehose(self, mock_write_stream_batch):
#         self._create_stream_data()

#         queue = QueueTestMock()
#         worker = Worker(queue, 2)

#         self.assertEqual(StreamData.objects.count(), 9)
#         queue.add_messages([
#             {
#                 'module': 'apps.streamtimeseries.worker.migrate',
#                 'class': 'MigrateDataAction',
#                 'arguments': {
#                     'migration_type': 'data',
#                     'stream_slug': self.s1.slug,
#                     'start': 5,
#                     'end': 6,
#                 }
#             }
#         ])
#         converted_data = DataConverter.data_to_tsvalue(self.sd11)
#         worker.run_once_without_delete()
#         self.assertEqual(StreamData.objects.count(), 9)
#         # new data isn't created since firehose payload is sent instead
#         self.assertEqual(StreamTimeSeriesValue.objects.count(), 0)
#         mock_write_stream_batch.assert_called_once_with([
#             {
#                 'Data': '{{"stream_slug": "{}", "project_id": {}, "device_id": {}, "variable_id": {}, "device_seqid": 5, "timestamp": "2016-09-28T10:00:10.000000Z", "status": "unk", "type": "Num", "raw_value": 5}}'
#                 .format(
#                     self.s1.slug,
#                     converted_data.project_id,
#                     converted_data.device_id,
#                     converted_data.variable_id,
#                 )
#             }
#         ])

#     def testMigrateEvents(self):
#         self._create_stream_events()

#         queue = QueueTestMock()
#         worker = Worker(queue, 2)

#         self.assertEqual(StreamEventData.objects.count(), 9)
#         queue.add_messages([
#             {
#                 'module': 'apps.streamtimeseries.worker.migrate',
#                 'class': 'MigrateDataAction',
#                 'arguments': {
#                     'migration_type': 'event',
#                     'stream_slug': self.s1.slug,
#                     'start': 6,
#                     'end': 10,
#                 }
#             }
#         ])
#         worker.run_once_without_delete()
#         self.assertEqual(StreamEventData.objects.count(), 9)
#         self.assertEqual(StreamTimeSeriesEvent.objects.count(), 4)
#         self.assertEqual(StreamTimeSeriesEvent.objects.filter(stream_slug=self.s1.slug).count(), 4)
#         stse = StreamTimeSeriesEvent.objects.first()
#         self.assertEqual(stse.stream_slug, self.s1.slug)
#         self.assertEqual(stse.timestamp, self.ts_now + timedelta(seconds=20))
#         self.assertEqual(stse.device_seqid, 6)
#         self.assertEqual(stse.extra_data, {'some_data': 6})

#         queue.delete_all()
#         queue.add_messages([
#             {
#                 'module': 'apps.streamtimeseries.worker.migrate',
#                 'class': 'MigrateDataAction',
#                 'arguments': {
#                     'migration_type': 'event',
#                     'stream_slug': self.s2.slug,
#                 }
#             }
#         ])
#         worker.run_once_without_delete()
#         self.assertEqual(StreamEventData.objects.count(), 9)
#         self.assertEqual(StreamTimeSeriesEvent.objects.count(), 7)
#         self.assertEqual(StreamTimeSeriesEvent.objects.filter(stream_slug=self.s2.slug).count(), 3)
#         stse = StreamTimeSeriesEvent.objects.filter(stream_slug=self.s2.slug).first()
#         self.assertEqual(stse.stream_slug, self.s2.slug)
#         self.assertEqual(stse.timestamp, self.ts_now + timedelta(seconds=10))
#         self.assertEqual(stse.device_seqid, 5)
#         self.assertEqual(stse.extra_data, {'some_data': 5})

#     @mock.patch.object(MigrateDataAction, '_write_stream_batch')
#     @override_settings(USE_FIREHOSE_STREAMTIMESERIES=True)
#     def testMigrateEventsUsingFirehose(self, mock_write_stream_batch):
#         self._create_stream_events()

#         queue = QueueTestMock()
#         worker = Worker(queue, 2)

#         self.assertEqual(StreamEventData.objects.count(), 9)
#         queue.add_messages([
#             {
#                 'module': 'apps.streamtimeseries.worker.migrate',
#                 'class': 'MigrateDataAction',
#                 'arguments': {
#                     'migration_type': 'event',
#                     'stream_slug': self.s1.slug,
#                     'start': 5,
#                     'end': 6,
#                 }
#             }
#         ])
#         converted_event = DataConverter.event_to_tsevent(self.se11)
#         worker.run_once_without_delete()
#         self.assertEqual(StreamEventData.objects.count(), 9)
#         # new event isn't created since firehose payload is sent instead
#         self.assertEqual(StreamTimeSeriesEvent.objects.count(), 0)
#         mock_write_stream_batch.assert_called_once_with([
#             {
#                 'Data': '{{"stream_slug": "{}", "project_id": {}, "device_id": {}, "variable_id": {}, "device_seqid": 5, "timestamp": "2016-09-28T10:00:10.000000Z", "status": "unk", "uuid": "{}", "s3_key_path": "", "ext": "json", "extra_data": "{{\\"some_data\\": 5}}", "format_version": 2}}'
#                 .format(
#                     self.s1.slug,
#                     converted_event.project_id,
#                     converted_event.device_id,
#                     converted_event.variable_id,
#                     converted_event.uuid,
#                 )
#             }
#         ])

#     def testException(self):
#         action = MigrateDataAction()
#         args_bad_migration_type = {
#             'migration_type': 'bad',
#             'stream_slug': self.s1.slug,
#         }

#         with self.assertRaises(WorkerActionHardError) as context:
#             msg = 'Wrong migration type bad'
#             action.execute(args_bad_migration_type)
#         self.assertTrue(msg in str(context.exception))
