import json
from pprint import pprint
from datetime import timedelta
from django.utils import timezone, dateparse
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from apps.utils.test_util import TestMixin
from apps.streamevent.models import StreamEventData
from apps.streamdata.models import StreamData

from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.utest.devices import TripDeviceMock
from apps.utils.data_mask.mask_utils import set_data_mask

from ..models import *
from ..worker.report_generator import *
from ..generator.end_of_trip.generator import EndOfTripReportGenerator, TripSummary

user_model = get_user_model()


class TripSummaryGeneratorActionTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()

        self.device_mock = TripDeviceMock()

        self.o2 = Org.objects.get(slug='user-org')
        self.p1 = Project.objects.get(name='Project 1')
        self.pd1 = self.p1.devices.first()

    def tearDown(self):
        self.device_mock.tearDown()
        self.userTestTearDown()

    def testMock(self):
        self.device_mock.testMock(self)

    def testComputeTimeActive(self):
        s_temp_stream = self.pd1.streamids.get(var_lid=0x5023)
        qs = StreamData.df_objects.filter(stream_slug=s_temp_stream.slug)
        df = qs.to_dataframe(['value',], index='timestamp')
        time_under300 = TripSummary.compute_time_active(df=df, condition_met_count=(df['value'] < 300).sum())
        self.assertEqual(time_under300, '0:20:00')
        time_above300 = TripSummary.compute_time_active(df=df, condition_met_count=(df['value'] > 300).sum())
        self.assertEqual(time_above300, '0:30:00')
        time_above1000 = TripSummary.compute_time_active(df=df, condition_met_count=(df['value'] > 1000).sum())
        self.assertEqual(time_above1000, '0:00:00')

    def testGeneratorPath(self):
        rpt = UserReport.objects.create(label='RPT1', generator='end_of_trip', org=self.o2, created_by=self.u2)
        module_path, class_name = ReportGenerator._generator_package_path(rpt.generator)
        self.assertEqual(module_path, 'apps.report.generator.end_of_trip.generator')
        self.assertEqual(class_name, 'EndOfTripReportGenerator')
        generator_class = ReportGenerator.get_generator_class(rpt)
        rg = generator_class([], rpt, timezone.now(), timezone.now())
        self.assertTrue(isinstance(rg, EndOfTripReportGenerator))

    def testTripSummaryDateRanges(self):
        trip = TripSummary(self.pd1)
        trip.calculate_trip_date_ranges()
        self.assertIsNotNone(trip.ts_start)
        self.assertIsNotNone(trip.ts_end)
        self.assertEqual(trip.ts_start, parse_datetime('2018-01-20T00:00:00Z'))
        self.assertEqual(trip.ts_end, parse_datetime('2018-01-25T00:00:00Z'))

    def testCalculateTripSummary(self):
        s_event_stream = self.pd1.streamids.get(var_lid=0x5020)
        s_temp_stream = self.pd1.streamids.get(var_lid=0x5023)
        trip = TripSummary(self.pd1)
        trip.calculate_trip_date_ranges()
        trip.add_stream('5020', s_event_stream)
        trip.add_stream('5023', s_temp_stream)
        trip.calculate_trip_summary_data(self.pd1.sg.ui_extra['analysis']['trip_summary'])
        self.assertEqual(trip.data['Device'], self.pd1.slug)
        self.assertEqual(trip.data['START (UTC)'], '2018-01-20 00:00:00')
        self.assertEqual(trip.data['END (UTC)'], '2018-01-25 00:00:00')
        self.assertEqual(trip.data['First event at (UTC)'], '2018-01-20 00:00:00')
        self.assertEqual(trip.data['Last event at (UTC)'], '2018-01-20 10:48:00')
        self.assertAlmostEqual(trip.data['Max Peak (G)'], 134.0966, delta=0.002)
        self.assertEqual(trip.data['DeltaV at Max Peak (in/s)'], -1.5 * 39.370)
        self.assertEqual(trip.data['MaxDeltaV (in/s)'], 2.0 * 39.370)
        self.assertAlmostEqual(trip.data['Peak at MaxDeltaV (G)'], 93.6536, delta=0.002)
        self.assertEqual(trip.data['TimeStamp(MaxPeak) (UTC)'], '2018-01-20 09:36:00')
        self.assertEqual(trip.data['TimeStamp(MaxDeltaV) (UTC)'], '2018-01-20 01:12:00')
        self.assertAlmostEqual(trip.data['Peak at MaxDeltaV (G)'], 93.6536, delta=0.002)
        self.assertAlmostEqual(trip.data['Max Temp (C)'], 29.48, delta=0.001)
        self.assertAlmostEqual(trip.data['Min Temp (C)'], 7.84, delta=0.001)
        self.assertAlmostEqual(trip.data['Median Temp (C)'], 28.48, delta=0.001)
        self.assertEqual(trip.data['Above 30C'], '0:00:00')
        self.assertEqual(trip.data['Below 17C'], '0:20:00')

    def testBasicProcessReportAction(self):
        config = {}
        rpt1 = UserReport.objects.create(
            label='RPT1',
            interval='d',
            generator='end_of_trip',
            config=config,
            created_by=self.u2,
            org=self.o2
        )

        action = ReportGeneratorAction()
        action.process_user_report(rpt1, start=None, end=None, orginal_sources=[self.pd1.slug,])
        self.assertEqual(len(action._msgs), 0)
        stream_slug = self.pd1.get_stream_slug_for(SYSTEM_VID['TRIP_SUMMARY'])
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream_slug).count(), 1)
        summary = StreamEventData.objects.filter(stream_slug=stream_slug).first()

        trip_data = summary.extra_data
        self.assertEqual(trip_data['Device'], self.pd1.slug)
        self.assertEqual(trip_data['START (UTC)'], '2018-01-20 00:00:00')
        self.assertEqual(trip_data['END (UTC)'], '2018-01-25 00:00:00')
        self.assertEqual(trip_data['First event at (UTC)'], '2018-01-20 00:00:00')
        self.assertEqual(trip_data['Last event at (UTC)'], '2018-01-20 10:48:00')
        self.assertAlmostEqual(trip_data['Max Peak (G)'], 134.0966, delta=0.002)
        self.assertEqual(trip_data['DeltaV at Max Peak (in/s)'], -1.5 * 39.370)
        self.assertEqual(trip_data['MaxDeltaV (in/s)'], 2.0 * 39.370)
        self.assertAlmostEqual(trip_data['Peak at MaxDeltaV (G)'], 93.6536, delta=0.002)
        self.assertEqual(trip_data['TimeStamp(MaxPeak) (UTC)'], '2018-01-20 09:36:00')
        self.assertEqual(trip_data['TimeStamp(MaxDeltaV) (UTC)'], '2018-01-20 01:12:00')
        self.assertAlmostEqual(trip_data['Max Temp (C)'], 29.48, delta=0.001)
        self.assertAlmostEqual(trip_data['Min Temp (C)'], 7.84, delta=0.001)
        self.assertAlmostEqual(trip_data['Median Temp (C)'], 28.48, delta=0.001)
        self.assertEqual(trip_data['Above 30C'], '0:00:00')
        self.assertEqual(trip_data['Below 17C'], '0:20:00')

        self.assertFalse('note' in trip_data)

    def testReportActionWithDataMask(self):
        config = {}
        rpt1 = UserReport.objects.create(
            label='RPT1',
            interval='d',
            generator='end_of_trip',
            config=config,
            created_by=self.u2,
            org=self.o2
        )

        # Set Data Mask
        set_data_mask(obj=self.pd1, start='2018-01-20T02:00:00Z', end=None,
                      event_excetions=[], data_exceptions=[], user=self.u1)

        action = ReportGeneratorAction()
        action.process_user_report(rpt1, start=None, end=None, orginal_sources=[self.pd1.slug,])
        self.assertEqual(len(action._msgs), 0)
        stream_slug = self.pd1.get_stream_slug_for(SYSTEM_VID['TRIP_SUMMARY'])
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream_slug).count(), 1)
        summary = StreamEventData.objects.filter(stream_slug=stream_slug).first()

        trip_data = summary.extra_data
        self.assertEqual(trip_data['Device'], self.pd1.slug)
        self.assertEqual(trip_data['START (UTC)'], '2018-01-20 02:00:00')
        self.assertEqual(trip_data['END (UTC)'], '2018-01-25 00:00:00')
        self.assertEqual(trip_data['First event at (UTC)'], '2018-01-20 02:24:00')
        self.assertEqual(trip_data['Last event at (UTC)'], '2018-01-20 10:48:00')
        self.assertAlmostEqual(trip_data['Max Peak (G)'], 134.0966, delta=0.002)
        self.assertEqual(trip_data['DeltaV at Max Peak (in/s)'], -1.5 * 39.370)
        self.assertAlmostEqual(trip_data['MaxDeltaV (in/s)'], 59.0549, delta=0.002)
        self.assertAlmostEqual(trip_data['Peak at MaxDeltaV (G)'], 133.199, delta=0.002)
        self.assertEqual(trip_data['TimeStamp(MaxPeak) (UTC)'], '2018-01-20 09:36:00')
        self.assertEqual(trip_data['TimeStamp(MaxDeltaV) (UTC)'], '2018-01-20 02:24:00')

        self.assertTrue('Notes' in trip_data)
        self.assertEqual('Trip Start and/or End was overwritten by a set device data mask', trip_data['Notes'])
