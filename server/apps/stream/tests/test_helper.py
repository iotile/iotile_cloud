import datetime
import json

import dateutil.parser

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import dateparse, timezone
from django.utils.dateparse import parse_datetime

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.physicaldevice.models import Device
from apps.projecttemplate.models import ProjectTemplate
from apps.streamdata.models import StreamData
from apps.utils.data_mask.mask_utils import set_data_mask
from apps.utils.gid.convert import *
from apps.utils.test_util import TestMixin
from apps.utils.timezone_utils import str_utc
from apps.vartype.models import *

from ..helpers import *
from ..models import *

user_model = get_user_model()


class StreamDataDisplayHelperTest(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=1,
        )
        self.d1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.s = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=self.d1, created_by=self.u2
        )

    def tearDown(self):
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testStreamDataHelperInput(self):
        helper = StreamDataDisplayHelper(self.s)

        self.v1.offset = 1.0
        self.v1.multiplication_factor = 1
        self.v1.division_factor = 2

        self.s.mdo_type = 'V'
        self.assertEqual(helper.input_value(10), 6.0)

        self.s.mdo_type = 'S'
        self.assertEqual(helper.input_value(10), 10.0)

        self.s.offset = 2.0
        self.s.mdo_type = 'S'
        self.assertEqual(helper.input_value(10), 12.0)

        self.s.multiplication_factor = 3
        self.s.division_factor = 2
        self.s.mdo_type = 'S'
        self.assertEqual(helper.input_value(10), 17.0)

        # Illegal values
        self.s.multiplication_factor = 0
        self.s.division_factor = 1
        self.s.mdo_type = 'S'
        self.assertEqual(helper.input_value('sum'), None)

        self.s.multiplication_factor = 3
        self.s.division_factor = 2
        self.s.mdo_type = 'V'
        self.assertEqual(helper.input_value('sum'), None)
        self.s.mdo_type = 'S'
        self.assertEqual(helper.input_value('sum'), None)

    def testStreamDataHelperOutputValue(self):
        helper = StreamDataDisplayHelper(self.s)

        self.v1.units = 'foo'
        self.v1.decimal_places = 0

        self.assertEqual(helper.output_value(10), 10)
        self.assertEqual(helper.format_value(10), '10')
        self.assertEqual(helper.format_value(10, True), '10 foo')

        self.assertEqual(helper.format_value(None), 'ERR')


class StreamDataQueryHelperTest(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=1,
        )
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        StreamId.objects.create_after_new_device(self.pd1)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()

        self.dt1 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        self.dt2 = dateutil.parser.parse('2016-09-28T11:00:00Z')
        self.dt3 = dateutil.parser.parse('2016-09-30T10:00:00Z')

        StreamData.objects.create(
            stream_slug=self.s1.slug,
            streamer_local_id=2,
            type='ITR',
            timestamp=self.dt2,
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            streamer_local_id=1,
            type='ITR',
            timestamp=self.dt1,
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            streamer_local_id=4,
            type='ITR',
            timestamp=self.dt3,
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            streamer_local_id=5,
            type='ITR',
            timestamp=self.dt3 + datetime.timedelta(seconds=10),
            int_value=8
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=self.dt3 + datetime.timedelta(seconds=40),
            streamer_local_id=10,
            int_value=9
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            streamer_local_id=8,
            type='ITR',
            timestamp=self.dt3 + datetime.timedelta(seconds=20),
            int_value=9
        )
        StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='ITR',
            timestamp=self.dt3 + datetime.timedelta(seconds=30),
            streamer_local_id=9,
            int_value=8
        )

    def tearDown(self):
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasicQuerySet(self):

        helper = StreamDataQueryHelper(self.s1)
        qs1 = helper._get_basic_data_qs()
        self.assertEqual(qs1.count(), 7)
        last = qs1.last()
        self.assertEqual(last.streamer_local_id, 10)

        qs2 = helper._sort_qs(qs1)
        self.assertEqual(qs2.count(), 7)
        last = qs2.first()
        self.assertEqual(last.streamer_local_id, 1)
        last = qs2.last()
        self.assertEqual(last.streamer_local_id, 10)

    def testBasicLastN(self):

        helper = StreamDataQueryHelper(self.s1)
        qs1 = helper._get_basic_data_qs()
        self.assertEqual(qs1.count(), 7)

        qs2 = helper._get_data_qs(qs=qs1, num=2)
        self.assertEqual(len(qs2), 2)
        first = qs2[0]
        self.assertEqual(first.streamer_local_id, 9)
        last = qs2[1]
        self.assertEqual(last.streamer_local_id, 10)

    def testBasicStartEnd(self):

        helper = StreamDataQueryHelper(self.s1)
        qs1 = helper._get_basic_data_qs()
        self.assertEqual(qs1.count(), 7)

        qs2 = helper._get_data_for_period_qs(qs=qs1, start=None, end='2016-09-28T11:00:01+00:00')
        qs2 = helper._sort_qs(qs2)
        self.assertEqual(qs2.count(), 2)
        first = qs2.first()
        self.assertEqual(first.streamer_local_id, 1)
        last = qs2.last()
        self.assertEqual(last.streamer_local_id, 2)

        qs2 = helper._get_data_for_period_qs(qs=qs1, start='2016-09-28T11:00:00+00:00', end=None)
        qs2 = helper._sort_qs(qs2)
        self.assertEqual(qs2.count(), 6)
        first = qs2.first()
        self.assertEqual(first.streamer_local_id, 2)
        last = qs2.last()
        self.assertEqual(last.streamer_local_id, 10)

        qs2 = helper._get_data_for_period_qs(qs=qs1, start='2016-09-28T11:00:00Z',
                                             end=self.dt3 + datetime.timedelta(seconds=20))
        qs2 = helper._sort_qs(qs2)
        self.assertEqual(qs2.count(), 3)
        first = qs2.first()
        self.assertEqual(first.streamer_local_id, 2)
        last = qs2.last()
        self.assertEqual(last.streamer_local_id, 5)

        qs2 = helper._get_data_for_period_qs(qs=qs1, start='2016-09-28T11:00:00Z', end='2016-09-28T11:00:01Z')
        self.assertEqual(qs2.count(), 1)
        first = qs2.first()
        self.assertEqual(first.streamer_local_id, 2)

    def testBasicLastNStartEnd(self):

        helper = StreamDataQueryHelper(self.s1)
        qs1 = helper._get_basic_data_qs()
        self.assertEqual(qs1.count(), 7)

        qs2 = helper._get_data_for_period_qs(qs=qs1, start=None, end=self.dt3 + datetime.timedelta(seconds=20))
        self.assertEqual(qs2.count(), 4)
        qs2 = helper._get_data_qs(qs=qs2, num=2)
        self.assertEqual(len(qs2), 2)
        first = qs2[0]
        self.assertEqual(first.streamer_local_id, 4)
        last = qs2[1]
        self.assertEqual(last.streamer_local_id, 5)

    def testStreamDataHelperDataMask(self):
        helper = StreamDataQueryHelper(self.s1)

        start, end = helper._get_start_and_end_dates({})
        self.assertIsNone(start)
        self.assertIsNone(end)

        start, end = helper._get_start_and_end_dates({'start': '2016-09-28T11:00:00Z'})
        self.assertEqual(str_utc(start), '2016-09-28T11:00:00Z')
        self.assertIsNone(end)
        start, end = helper._get_start_and_end_dates({'end': '2016-09-28T11:00:00Z'})
        self.assertIsNone(start)
        self.assertEqual(str_utc(end), '2016-09-28T11:00:00Z')
        start, end = helper._get_start_and_end_dates({'start': '2016-09-28T11:00:00Z', 'end': '2017-09-28T11:00:00Z'})
        self.assertEqual(str_utc(start), '2016-09-28T11:00:00Z')
        self.assertEqual(str_utc(end), '2017-09-28T11:00:00Z')

        # Now with a mask
        set_data_mask(self.s1.device, '2016-10-28T11:00:00Z', None, [], [], user=self.u1)

        start, end = helper._get_start_and_end_dates({'start': '2016-09-28T11:00:00Z'})
        self.assertEqual(str_utc(start), '2016-10-28T11:00:00Z')
        self.assertIsNone(end)
        start, end = helper._get_start_and_end_dates({'end': '2016-09-28T11:00:00Z'})
        self.assertEqual(str_utc(start), '2016-10-28T11:00:00Z')
        self.assertEqual(str_utc(end), '2016-09-28T11:00:00Z')
        start, end = helper._get_start_and_end_dates({'start': '2016-09-28T11:00:00Z', 'end': '2017-09-28T11:00:00Z'})
        self.assertEqual(str_utc(start), '2016-10-28T11:00:00Z')
        self.assertEqual(str_utc(end), '2017-09-28T11:00:00Z')

        # Now with a mask
        set_data_mask(self.s1.device, '2016-10-28T11:00:00Z', '2017-08-28T11:00:00Z', [], [], user=self.u1)

        start, end = helper._get_start_and_end_dates({'start': '2016-09-28T11:00:00Z'})
        self.assertEqual(str_utc(start), '2016-10-28T11:00:00Z')
        self.assertEqual(str_utc(end), '2017-08-28T11:00:00Z')
        start, end = helper._get_start_and_end_dates({'end': '2016-09-28T11:00:00Z'})
        self.assertEqual(str_utc(start), '2016-10-28T11:00:00Z')
        self.assertEqual(str_utc(end), '2016-09-28T11:00:00Z')
        start, end = helper._get_start_and_end_dates({'start': '2016-09-28T11:00:00Z', 'end': '2017-09-28T11:00:00Z'})
        self.assertEqual(str_utc(start), '2016-10-28T11:00:00Z')
        self.assertEqual(str_utc(end), '2017-08-28T11:00:00Z')

        start, end = helper._get_start_and_end_dates({'start': '2016-11-28T11:00:00Z', 'end': '2017-07-28T11:00:00Z'})
        self.assertEqual(str_utc(start), '2016-11-28T11:00:00Z')
        self.assertEqual(str_utc(end), '2017-07-28T11:00:00Z')


    def testPublicApi(self):

        helper = StreamDataQueryHelper(self.s1)

        args = {}
        qs = helper.get_data_for_filter(args)
        self.assertEqual(qs.count(), 7)

        args = {
            'lastn': 2
        }
        qs = helper.get_data_for_filter(args)
        self.assertEqual(len(qs), 2)
        first = qs[0]
        self.assertEqual(first.streamer_local_id, 9)
        last = qs[1]
        self.assertEqual(last.streamer_local_id, 10)

        args = {
            'lastn': 2,
            'end': '2016-09-28T11:00:01Z'
        }
        qs = helper.get_data_for_filter(args)
        self.assertEqual(len(qs), 2)
        first = qs[0]
        self.assertEqual(first.streamer_local_id, 1)
        last = qs[1]
        self.assertEqual(last.streamer_local_id, 2)

        args = {
            'lastn': 2,
            'start': '2016-09-28T11:00:00Z',
            'end': str(self.dt3 + datetime.timedelta(seconds=20))
        }
        qs = helper.get_data_for_filter(args)
        self.assertEqual(len(qs), 2)
        first = qs[0]
        self.assertEqual(first.streamer_local_id, 4)
        last = qs[1]
        self.assertEqual(last.streamer_local_id, 5)

        args = {
            'start': '2016-09-28T11:00:00Z',
            'end': str(self.dt3 + datetime.timedelta(seconds=20))
        }
        qs = helper.get_data_for_filter(args)
        self.assertEqual(len(qs), 3)
        first = qs[0]
        self.assertEqual(first.streamer_local_id, 2)
        second = qs[1]
        self.assertEqual(second.streamer_local_id, 4)
        last = qs[2]
        self.assertEqual(last.streamer_local_id, 5)
