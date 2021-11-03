# import json
# import uuid

# import dateutil.parser
# from django.test import TestCase
# from django.utils import timezone

# from apps.streamdata.models import StreamData
# from apps.streamevent.models import StreamEventData
# from apps.streamtimeseries.models import StreamTimeSeriesEvent, StreamTimeSeriesValue
# from apps.utils.data_helpers.convert import DataConverter


# class DataConverterTestCase(TestCase):

#     def setUp(self):
#         self.dt = dateutil.parser.parse('2016-09-28T10:00:00.000000Z')

#         self.sd1 = StreamData(
#             stream_slug='s--0000-0008--0000-0000-0000-0053--5003',
#             project_slug='p--0000-0008',
#             device_slug='d--0000-0000-0000-0053',
#             variable_slug='v--0000-0008--5003',
#             device_timestamp=424242,
#             timestamp=self.dt.replace(tzinfo=None),
#             streamer_local_id=4552,
#             dirty_ts=False,
#             status='unk',
#             type='ITR',
#             value=67.8632478632479,
#             int_value=2779,
#         )

#         self.stsv1 = StreamTimeSeriesValue(
#             stream_slug='s--0000-0008--0000-0000-0000-0053--5003',
#             project_id=8,
#             device_id=83,
#             block_id=None,
#             variable_id=20483,
#             device_seqid=4552,
#             device_timestamp=424242,
#             timestamp=self.dt,
#             status='unk',
#             type='ITR',
#             value=67.8632478632479,
#             raw_value=2779,
#         )

#         self.sd2 = StreamData(
#             stream_slug='s--0000-0000--0001-0000-0000-0051--5001',
#             project_slug='',
#             device_slug='b--0001-0000-0000-0051',
#             variable_slug='v--0000-0007--5001',
#             device_timestamp=None,
#             timestamp=self.dt,
#             streamer_local_id=32,
#             dirty_ts=False,
#             status='unk',
#             type='ITR',
#             value=0.0,
#             int_value=0,
#         )

#         self.stsv2 = StreamTimeSeriesValue(
#             stream_slug='s--0000-0000--0001-0000-0000-0051--5001',
#             project_id=None,
#             device_id=81,
#             block_id=1,
#             variable_id=20481,
#             device_seqid=32,
#             device_timestamp=None,
#             timestamp=self.dt,
#             status='unk',
#             type='ITR',
#             value=0.0,
#             raw_value=0,
#         )

#         self.se1 = StreamEventData(
#             stream_slug='s--0000-0110--0000-0000-0000-0528--5020',
#             project_slug='p--0000-0110',
#             device_slug='d--0000-0000-0000-0528',
#             variable_slug='v--0000-0110--5020',
#             device_timestamp=91600,
#             timestamp=self.dt,
#             streamer_local_id=36359,
#             dirty_ts=False,
#             status='cln',
#             uuid=uuid.UUID('3f2e74e2-1f56-4235-afc1-77aad2665878'),
#             s3_key_path='',
#             ext='json',
#             format_version=2,
#             extra_data={
#                 'axis': 'z',
#                 'peak': 17.787,
#                 'duration': 2,
#                 'delta_v_x': 0.025665283203125,
#                 'delta_v_y': -0.1455230712890625,
#                 'delta_v_z': 0.2067718505859375,
#             },
#         )

#         self.se2 = StreamEventData(
#             stream_slug='s--0000-0000--0001-0000-0000-0801--5020',
#             project_slug='',
#             device_slug='b--0001-0000-0000-0801',
#             variable_slug='v--0000-017f--5020',
#             device_timestamp=168862,
#             timestamp=self.dt,
#             streamer_local_id=1901540,
#             dirty_ts=False,
#             status='unk',
#             uuid=uuid.UUID('3e44350f-9baa-41cb-95e5-8b07709b854e'),
#             s3_key_path='2018/11/03/01',
#             ext='json',
#             format_version=2,
#             extra_data={
#                 'axis': 'y',
#                 'peak': 5.88,
#                 'duration': 13.125,
#                 'delta_v_x': -0.3973348122187501,
#                 'delta_v_y': -0.216687125484375,
#                 'delta_v_z': -1.7794472882812506,
#             },
#         )

#         self.stse1 = StreamTimeSeriesEvent(
#             stream_slug='s--0000-0110--0000-0000-0000-0528--5020',
#             project_id=272,
#             device_id=1320,
#             block_id=None,
#             variable_id=20512,
#             device_seqid=36359,
#             device_timestamp=91600,
#             timestamp=self.dt,
#             status='cln',
#             uuid='3f2e74e2-1f56-4235-afc1-77aad2665878',
#             s3_key_path='',
#             ext='json',
#             format_version=2,
#             extra_data={
#                 'axis': 'z',
#                 'peak': 17.787,
#                 'duration': 2,
#                 'delta_v_x': 0.025665283203125,
#                 'delta_v_y': -0.1455230712890625,
#                 'delta_v_z': 0.2067718505859375,
#             },
#         )

#         self.stse2 = StreamTimeSeriesEvent(
#             stream_slug='s--0000-0000--0001-0000-0000-0801--5020',
#             project_id=None,
#             device_id=2049,
#             block_id=1,
#             variable_id=20512,
#             device_seqid=1901540,
#             device_timestamp=168862,
#             timestamp=self.dt,
#             status='unk',
#             uuid='3e44350f-9baa-41cb-95e5-8b07709b854e',
#             s3_key_path='2018/11/03/01',
#             ext='json',
#             format_version=2,
#             extra_data={
#                 'axis': 'y',
#                 'peak': 5.88,
#                 'duration': 13.125,
#                 'delta_v_x': -0.3973348122187501,
#                 'delta_v_y': -0.216687125484375,
#                 'delta_v_z': -1.7794472882812506,
#             },
#         )

#     def tearDown(self):
#         StreamData.objects.all().delete()
#         StreamTimeSeriesValue.objects.all().delete()
#         StreamEventData.objects.all().delete()
#         StreamTimeSeriesEvent.objects.all().delete()

#     def testConvertDataToTimeSeries(self):
#         converted1 = DataConverter.data_to_tsvalue(self.sd1)
#         self.assertEqual(converted1.stream_slug, 's--0000-0008--0000-0000-0000-0053--5003')
#         self.assertEqual(converted1.project_id, 8)
#         self.assertEqual(converted1.device_id, 83)
#         self.assertEqual(converted1.block_id, None)
#         self.assertEqual(converted1.variable_id, 20483)
#         self.assertEqual(converted1.device_seqid, 4552)
#         self.assertEqual(converted1.device_timestamp, 424242)
#         self.assertEqual(converted1.timestamp, self.dt)
#         self.assertEqual(converted1.status, 'unk')
#         self.assertEqual(converted1.type, 'ITR')
#         self.assertAlmostEqual(converted1.value, 67.8632478632479)
#         self.assertEqual(converted1.raw_value, 2779)

#         converted2 = DataConverter.data_to_tsvalue(self.sd2)
#         self.assertEqual(converted2.stream_slug, 's--0000-0000--0001-0000-0000-0051--5001')
#         self.assertEqual(converted2.project_id, None)
#         self.assertEqual(converted2.device_id, 81)
#         self.assertEqual(converted2.block_id, 1)
#         self.assertEqual(converted2.variable_id, 20481)
#         self.assertEqual(converted2.device_seqid, 32)
#         self.assertEqual(converted2.device_timestamp, None)
#         self.assertEqual(converted2.timestamp, self.dt)
#         self.assertEqual(converted2.status, 'unk')
#         self.assertEqual(converted2.type, 'ITR')
#         self.assertAlmostEqual(converted2.value, 0.0)
#         self.assertEqual(converted2.raw_value, 0)

#     def testConvertTimeSeriesToData(self):
#         converted1 = DataConverter.tsvalue_to_data(self.stsv1)
#         self.assertEqual(converted1.stream_slug, 's--0000-0008--0000-0000-0000-0053--5003')
#         self.assertEqual(converted1.project_slug, 'p--0000-0008')
#         self.assertEqual(converted1.device_slug, 'd--0000-0000-0000-0053')
#         self.assertEqual(converted1.variable_slug, 'v--0000-0008--5003')
#         self.assertEqual(converted1.device_timestamp, 424242)
#         self.assertEqual(converted1.timestamp, self.dt)
#         self.assertEqual(converted1.streamer_local_id, 4552)
#         self.assertEqual(converted1.dirty_ts, False)
#         self.assertEqual(converted1.status, 'unk')
#         self.assertEqual(converted1.type, 'ITR')
#         self.assertAlmostEqual(converted1.value, 67.8632478632479)
#         self.assertEqual(converted1.int_value, 2779)

#         converted2 = DataConverter.tsvalue_to_data(self.stsv2)
#         self.assertEqual(converted2.stream_slug, 's--0000-0000--0001-0000-0000-0051--5001')
#         self.assertEqual(converted2.project_slug, '')
#         self.assertEqual(converted2.device_slug, 'b--0001-0000-0000-0051')
#         self.assertEqual(converted2.variable_slug, '')
#         self.assertEqual(converted2.device_timestamp, None)
#         self.assertEqual(converted2.timestamp, self.dt)
#         self.assertEqual(converted2.streamer_local_id, 32)
#         self.assertEqual(converted2.dirty_ts, False)
#         self.assertEqual(converted2.status, 'unk')
#         self.assertEqual(converted2.type, 'ITR')
#         self.assertAlmostEqual(converted2.value, 0.0)
#         self.assertEqual(converted2.int_value, 0)

#     def testConvertEventToTimeSeries(self):
#         converted1 = DataConverter.event_to_tsevent(self.se1)
#         self.assertEqual(converted1.stream_slug, 's--0000-0110--0000-0000-0000-0528--5020')
#         self.assertEqual(converted1.project_id, 272)
#         self.assertEqual(converted1.device_id, 1320)
#         self.assertEqual(converted1.block_id, None)
#         self.assertEqual(converted1.variable_id, 20512)
#         self.assertEqual(converted1.device_seqid, 36359)
#         self.assertEqual(converted1.device_timestamp, 91600)
#         self.assertEqual(converted1.timestamp, self.dt)
#         self.assertEqual(converted1.status, 'cln')
#         self.assertEqual(converted1.uuid, '3f2e74e2-1f56-4235-afc1-77aad2665878')
#         self.assertEqual(converted1.s3_key_path, '')
#         self.assertEqual(converted1.ext, 'json')
#         self.assertEqual(converted1.format_version, 2)
#         self.assertEqual(converted1.extra_data['axis'], 'z')
#         self.assertAlmostEqual(converted1.extra_data['peak'], 17.787)
#         self.assertAlmostEqual(converted1.extra_data['duration'], 2)
#         self.assertAlmostEqual(converted1.extra_data['delta_v_x'], 0.025665283203125)
#         self.assertAlmostEqual(converted1.extra_data['delta_v_y'], -0.1455230712890625)
#         self.assertAlmostEqual(converted1.extra_data['delta_v_z'], 0.2067718505859375)

#         converted2 = DataConverter.event_to_tsevent(self.se2)
#         self.assertEqual(converted2.stream_slug, 's--0000-0000--0001-0000-0000-0801--5020')
#         self.assertEqual(converted2.project_id, None)
#         self.assertEqual(converted2.device_id, 2049)
#         self.assertEqual(converted2.block_id, 1)
#         self.assertEqual(converted2.variable_id, 20512)
#         self.assertEqual(converted2.device_seqid, 1901540)
#         self.assertEqual(converted2.device_timestamp, 168862)
#         self.assertEqual(converted2.timestamp, self.dt)
#         self.assertEqual(converted2.status, 'unk')
#         self.assertEqual(converted2.uuid, '3e44350f-9baa-41cb-95e5-8b07709b854e')
#         self.assertEqual(converted2.s3_key_path, '2018/11/03/01')
#         self.assertEqual(converted2.ext, 'json')
#         self.assertEqual(converted2.format_version, 2)
#         self.assertEqual(converted2.extra_data['axis'], 'y')
#         self.assertAlmostEqual(converted2.extra_data['peak'], 5.88)
#         self.assertAlmostEqual(converted2.extra_data['duration'], 13.125)
#         self.assertAlmostEqual(converted2.extra_data['delta_v_x'], -0.3973348122187501)
#         self.assertAlmostEqual(converted2.extra_data['delta_v_y'], -0.216687125484375)
#         self.assertAlmostEqual(converted2.extra_data['delta_v_z'], -1.7794472882812506)

#     def testConvertTimeSeriesToEvent(self):
#         converted1 = DataConverter.tsevent_to_event(self.stse1)
#         self.assertEqual(converted1.stream_slug, 's--0000-0110--0000-0000-0000-0528--5020')
#         self.assertEqual(converted1.project_slug, 'p--0000-0110')
#         self.assertEqual(converted1.device_slug, 'd--0000-0000-0000-0528')
#         self.assertEqual(converted1.variable_slug, 'v--0000-0110--5020')
#         self.assertEqual(converted1.device_timestamp, 91600)
#         self.assertEqual(converted1.timestamp, self.dt)
#         self.assertEqual(converted1.streamer_local_id, 36359)
#         self.assertEqual(converted1.dirty_ts, False)
#         self.assertEqual(converted1.status, 'cln')
#         self.assertEqual(converted1.uuid, uuid.UUID('3f2e74e2-1f56-4235-afc1-77aad2665878'))
#         self.assertEqual(converted1.s3_key_path, '')
#         self.assertEqual(converted1.ext, 'json')
#         self.assertEqual(converted1.format_version, 2)
#         self.assertEqual(converted1.extra_data['axis'], 'z')
#         self.assertAlmostEqual(converted1.extra_data['peak'], 17.787)
#         self.assertAlmostEqual(converted1.extra_data['duration'], 2)
#         self.assertAlmostEqual(converted1.extra_data['delta_v_x'], 0.025665283203125)
#         self.assertAlmostEqual(converted1.extra_data['delta_v_y'], -0.1455230712890625)
#         self.assertAlmostEqual(converted1.extra_data['delta_v_z'], 0.2067718505859375)

#         converted2 = DataConverter.tsevent_to_event(self.stse2)
#         self.assertEqual(converted2.stream_slug, 's--0000-0000--0001-0000-0000-0801--5020')
#         self.assertEqual(converted2.project_slug, '')
#         self.assertEqual(converted2.device_slug, 'b--0001-0000-0000-0801')
#         self.assertEqual(converted2.variable_slug, '')
#         self.assertEqual(converted2.device_timestamp, 168862)
#         self.assertEqual(converted2.timestamp, self.dt)
#         self.assertEqual(converted2.status, 'unk')
#         self.assertEqual(converted2.uuid, uuid.UUID('3e44350f-9baa-41cb-95e5-8b07709b854e'))
#         self.assertEqual(converted2.s3_key_path, '2018/11/03/01')
#         self.assertEqual(converted2.ext, 'json')
#         self.assertEqual(converted2.format_version, 2)
#         self.assertEqual(converted2.extra_data['axis'], 'y')
#         self.assertAlmostEqual(converted2.extra_data['peak'], 5.88)
#         self.assertAlmostEqual(converted2.extra_data['duration'], 13.125)
#         self.assertAlmostEqual(converted2.extra_data['delta_v_x'], -0.3973348122187501)
#         self.assertAlmostEqual(converted2.extra_data['delta_v_y'], -0.216687125484375)
#         self.assertAlmostEqual(converted2.extra_data['delta_v_z'], -1.7794472882812506)

#     def testConvertTimeSeriesDataToFirehosePayload(self):
#         converted1 = DataConverter.tsvalue_to_firehose(self.stsv1)
#         # check that converted1 is JSON-serializable
#         json.dumps(converted1)
#         self.assertEqual(converted1['stream_slug'], 's--0000-0008--0000-0000-0000-0053--5003')
#         self.assertEqual(converted1['project_id'], 8)
#         self.assertEqual(converted1['device_id'], 83)
#         self.assertFalse('block_id' in converted1)
#         self.assertEqual(converted1['variable_id'], 20483)
#         self.assertEqual(converted1['device_seqid'], 4552)
#         self.assertEqual(converted1['device_timestamp'], 424242)
#         self.assertEqual(converted1['timestamp'], '2016-09-28T10:00:00.000000Z')
#         self.assertEqual(converted1['status'], 'unk')
#         self.assertEqual(converted1['type'], 'ITR')
#         self.assertAlmostEqual(converted1['value'], 67.8632478632479)
#         self.assertEqual(converted1['raw_value'], 2779)

#         converted2 = DataConverter.tsvalue_to_firehose(self.stsv2)
#         # check that converted2 is JSON-serializable
#         json.dumps(converted2)
#         self.assertEqual(converted2['stream_slug'], 's--0000-0000--0001-0000-0000-0051--5001')
#         self.assertFalse('project_id' in converted2)
#         self.assertEqual(converted2['device_id'], 81)
#         self.assertEqual(converted2['block_id'], 1)
#         self.assertEqual(converted2['variable_id'], 20481)
#         self.assertEqual(converted2['device_seqid'], 32)
#         self.assertFalse('device_timestamp' in converted2)
#         self.assertEqual(converted2['timestamp'], '2016-09-28T10:00:00.000000Z')
#         self.assertEqual(converted2['status'], 'unk')
#         self.assertEqual(converted2['type'], 'ITR')
#         self.assertAlmostEqual(converted2['value'], 0.0)
#         self.assertEqual(converted2['raw_value'], 0)

#     def testConvertTimeSeriesEventToFirehosePayload(self):
#         converted1 = DataConverter.tsevent_to_firehose(self.stse1)
#         # check that converted1 is JSON-serializable
#         json.dumps(converted1)
#         self.assertEqual(converted1['stream_slug'], 's--0000-0110--0000-0000-0000-0528--5020')
#         self.assertEqual(converted1['project_id'], 272)
#         self.assertEqual(converted1['device_id'], 1320)
#         self.assertFalse('block_id' in converted1)
#         self.assertEqual(converted1['variable_id'], 20512)
#         self.assertEqual(converted1['device_seqid'], 36359)
#         self.assertEqual(converted1['device_timestamp'], 91600)
#         self.assertEqual(converted1['timestamp'], '2016-09-28T10:00:00.000000Z')
#         self.assertEqual(converted1['status'], 'cln')
#         self.assertEqual(converted1['uuid'], '3f2e74e2-1f56-4235-afc1-77aad2665878')
#         self.assertEqual(converted1['s3_key_path'], '')
#         self.assertEqual(converted1['ext'], 'json')
#         self.assertEqual(converted1['format_version'], 2)
#         self.assertEqual(converted1['extra_data'],
#                          '{"axis": "z", "peak": 17.787, "duration": 2, "delta_v_x": 0.025665283203125, "delta_v_y": -0.1455230712890625, "delta_v_z": 0.2067718505859375}')

#         converted2 = DataConverter.tsevent_to_firehose(self.stse2)
#         # check that converted2 is JSON-serializable
#         json.dumps(converted2)
#         self.assertEqual(converted2['stream_slug'], 's--0000-0000--0001-0000-0000-0801--5020')
#         self.assertFalse('project_id' in converted2)
#         self.assertEqual(converted2['device_id'], 2049)
#         self.assertEqual(converted2['block_id'], 1)
#         self.assertEqual(converted2['variable_id'], 20512)
#         self.assertEqual(converted2['device_seqid'], 1901540)
#         self.assertEqual(converted2['device_timestamp'], 168862)
#         self.assertEqual(converted2['timestamp'], '2016-09-28T10:00:00.000000Z')
#         self.assertEqual(converted2['status'], 'unk')
#         self.assertEqual(converted2['uuid'], '3e44350f-9baa-41cb-95e5-8b07709b854e')
#         self.assertEqual(converted2['s3_key_path'], '2018/11/03/01')
#         self.assertEqual(converted2['ext'], 'json')
#         self.assertEqual(converted2['format_version'], 2)
#         self.assertEqual(converted2['extra_data'],
#                          '{"axis": "y", "peak": 5.88, "duration": 13.125, "delta_v_x": -0.3973348122187501, "delta_v_y": -0.216687125484375, "delta_v_z": -1.7794472882812506}')
