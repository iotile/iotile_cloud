import datetime
import json
import struct

import dateutil.parser

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.devicetemplate.models import DeviceTemplate
from apps.physicaldevice.models import Device
from apps.stream.helpers import StreamDataDisplayHelper, StreamDataQueryHelper
from apps.stream.models import CTYPE_TO_RAW_FORMAT, StreamId, StreamVariable
from apps.streamfilter.models import *
from apps.utils.gid.convert import *
from apps.utils.mdo.helpers import MdoHelper
from apps.utils.test_util import TestMixin
from apps.vartype.models import VarType, VarTypeInputUnit, VarTypeOutputUnit

from ..helpers import StreamDataBuilderHelper
from ..models import *
from ..utils import get_stream_input_mdo, get_stream_mdo, get_stream_output_mdo

user_model = get_user_model()


class StreamDataBuilderHelperTestCase(TestMixin, TestCase):

    def setUp(self):
        self.u = user_model.objects.create_user(username='User2', email='user2@foo.com', password='pass')
        self.u.is_active = True
        self.u.save()
        o = Org.objects.create_org(name='Org 1', created_by=self.u)
        dt = DeviceTemplate.objects.create(external_sku='Device Template', org=o,
                                           released_on=datetime.datetime.utcnow(),
                                           created_by=self.u)
        self.p = Project.objects.create(name='Project 1', created_by=self.u, org=o)
        self.v = StreamVariable.objects.create_variable(
            name='Var A', project=self.p, created_by=self.u, lid=0x5001,
        )
        self.d = Device.objects.create_device(id=0xa, project=self.p, label='d1', template=dt, created_by=self.u)
        self.var_type = VarType.objects.create(
            name='Volume',
            storage_units_full='Liters',
            created_by=self.u
        )
        self.input_unit1 = VarTypeInputUnit.objects.create(
            var_type=self.var_type,
            unit_full='Liters',
            unit_short='l',
            m=1,
            d=2,
            created_by=self.u
        )
        self.input_unit2 = VarTypeInputUnit.objects.create(
            var_type=self.var_type,
            unit_full='Gallons',
            unit_short='g',
            m=4,
            d=2,
            created_by=self.u
        )


    def tearDown(self):
        StreamData.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        DeviceTemplate.objects.all().delete()
        Project.objects.all().delete()
        Org.objects.all().delete()
        OrgMembership.objects.all().delete()
        VarTypeInputUnit.objects.all().delete()
        VarType.objects.all().delete()

    def testDeduceSlugs(self):
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        data = StreamData(
            stream_slug='s--0000-0001--0000-0000-0000-0123--5001',
            type='Num',
            timestamp=t0,
            int_value=6
        )
        data.deduce_slugs_from_stream_id()
        self.assertEqual(data.device_slug, 'd--0000-0000-0000-0123')
        self.assertEqual(data.project_slug, 'p--0000-0001')
        self.assertEqual(data.variable_slug, 'v--0000-0001--5001')

        data.stream_slug = 's--0000-0000--0001-0000-0000-0123--5001'
        data.deduce_slugs_from_stream_id()
        self.assertEqual(data.device_slug, 'b--0001-0000-0000-0123')
        self.assertEqual(data.project_slug, '')
        self.assertEqual(data.variable_slug, 'v--0000-0000--5001')

    def testBuildData(self):
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        helper = StreamDataBuilderHelper()
        stream_data = helper.build_data_obj(
            stream_slug='s--0000-0001--0000-0000-0000-0001--0001',
            type='Num',
            timestamp=t0,
            int_value=5
        )
        self.assertEqual(stream_data.int_value, 5)
        self.assertEqual(stream_data.value, 5.0)
        self.assertEqual(stream_data.type, 'Num')
        self.assertEqual(stream_data.timestamp, t0)

        s = StreamId.objects.create(device=self.d, variable=self.v, project=self.p, created_by=self.u)
        stream_data = helper.build_data_obj(
            stream_slug=s.slug,
            timestamp=t0,
            int_value=5
        )
        self.assertEqual(stream_data.int_value, 5)
        self.assertEqual(stream_data.value, 5.0)
        self.assertEqual(stream_data.type, 'Num')
        self.assertEqual(stream_data.timestamp, t0)

    def testOldScheme(self):
        s = StreamId.objects.create(device=self.d, variable=self.v, project=self.p, created_by=self.u)
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        helper = StreamDataBuilderHelper()
        stream_data = helper.build_data_obj(
            stream_slug=s.slug,
            timestamp=t0,
            int_value=5
        )
        self.assertEqual(stream_data.int_value, 5)
        self.assertEqual(stream_data.type, 'Num')
        self.assertEqual(stream_data.value, 5.0)

        self.v.multiplication_factor = 5
        self.v.save()
        s.mdo_type = 'V'
        s.save()
        helper._streams = {}
        helper.add_stream(s)
        stream_data = helper.convert_to_internal_value(stream_data)
        self.assertEqual(stream_data.int_value, 5)
        self.assertEqual(stream_data.type, 'Num')
        self.assertEqual(stream_data.value, 25.0)

        s.mdo_type = 'S'
        s.multiplication_factor = 3
        s.save()
        helper._streams = {}
        helper.add_stream(s)
        stream_data = helper.convert_to_internal_value(stream_data)
        self.assertEqual(stream_data.int_value, 5)
        self.assertEqual(stream_data.type, 'Num')
        self.assertEqual(stream_data.value, 15.0)

    def testNewScheme(self):
        s = StreamId.objects.create(device=self.d, variable=self.v, project=self.p, created_by=self.u)
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        helper = StreamDataBuilderHelper()
        stream_data = helper.build_data_obj(
            stream_slug=s.slug,
            timestamp=t0,
            int_value=5
        )
        self.assertEqual(stream_data.int_value, 5)
        self.assertEqual(stream_data.type, 'Num')
        self.assertEqual(stream_data.value, 5.0)

        self.v.multiplication_factor = 5
        self.v.var_type = self.var_type
        self.v.input_unit = self.input_unit1
        self.v.save()
        s.mdo_type = 'V'
        s.save()
        helper._streams = {}
        helper.add_stream(s)
        stream_data = helper.convert_to_internal_value(stream_data)
        self.assertEqual(stream_data.int_value, 5)
        self.assertEqual(stream_data.type, 'ITR')
        self.assertEqual(stream_data.value, 12.5)

        s.mdo_type = 'S'
        s.multiplication_factor = 3
        s.save()
        helper._streams = {}
        helper.add_stream(s)
        stream_data = helper.convert_to_internal_value(stream_data)
        self.assertEqual(stream_data.int_value, 5)
        self.assertEqual(stream_data.type, 'ITR')
        self.assertEqual(stream_data.value, 7.5)

        s.mdo_type = 'S'
        s.input_unit = self.input_unit2
        s.save()
        helper._streams = {}
        helper.add_stream(s)
        stream_data = helper.convert_to_internal_value(stream_data)
        self.assertEqual(stream_data.int_value, 5)
        self.assertEqual(stream_data.type, 'ITR')
        self.assertEqual(stream_data.value, 30.0)

    def testCasting(self):
        helper = StreamDataBuilderHelper()
        neg_five = 0xFFFFFFFB # -5
        raw_value = struct.pack('<L', neg_five)
        (uint_value,) = struct.unpack('<L', raw_value)
        (int_value,) = struct.unpack('<l', raw_value)
        self.assertEqual(uint_value, neg_five)
        self.assertEqual(int_value, -5)
        self.assertEqual(helper._cast('<l', neg_five), -5)

        # Out of bounds
        self.assertEqual(helper._cast('<L', 0xffffffff), 2147483647)
        self.assertEqual(helper._cast('auto', 4147483647), 2147483647)
        self.assertEqual(helper._cast('auto', -4147483647), -2147483647)

    def testValueCType(self):
        s = StreamId.objects.create(device=self.d, variable=self.v, project=self.p, created_by=self.u)
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        helper = StreamDataBuilderHelper()
        neg_five = 0xFFFFFFFB # -5
        stream_data = helper.build_data_obj(
            stream_slug=s.slug,
            timestamp=t0,
            int_value=neg_five
        )
        s.mdo_type = 'S'
        s.input_unit = self.input_unit1
        s.multiplication_factor = 3
        s.raw_value_format = CTYPE_TO_RAW_FORMAT['int']
        s.save()
        helper._streams = {}
        helper.add_stream(s)
        stream_data = helper.convert_to_internal_value(stream_data)
        self.assertEqual(stream_data.int_value, neg_five)
        self.assertEqual(stream_data.type, 'ITR')
        self.assertEqual(stream_data.value, -7.5)

    def testMultiStream(self):
        self.v.multiplication_factor = 5
        self.v.var_type = self.var_type
        self.v.input_unit = self.input_unit1
        self.v.save()
        s1 = StreamId.objects.create(device=self.d, variable=self.v, project=self.p, created_by=self.u, mdo_type = 'V')
        v2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p, created_by=self.u, lid=0x5002,
        )
        s2 = StreamId.objects.create(device=self.d, variable=v2, project=self.p, created_by=self.u,
                                     mdo_type = 'S', multiplication_factor = 3,
                                     input_unit = self.input_unit2)
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        t1 = dateutil.parser.parse('2016-09-28T10:01:00Z')
        t2 = dateutil.parser.parse('2016-09-28T10:02:00Z')
        helper = StreamDataBuilderHelper()
        d1 = helper.build_data_obj(
            stream_slug=s1.slug,
            type='Num',
            device_timestamp=0,
            timestamp=t0,
            int_value=5
        )
        d2 = helper.build_data_obj(
            stream_slug=s1.slug,
            type='Num',
            device_timestamp=60,
            timestamp=t1,
            int_value=10
        )
        d3 = helper.build_data_obj(
            stream_slug='s--0000-0001--0000-0000-0000-0001--0001',
            type='Num',
            device_timestamp=120,
            timestamp=t2,
            int_value=2
        )
        d4 = helper.build_data_obj(
            stream_slug=s2.slug,
            type='Num',
            device_timestamp=120,
            timestamp=t2,
            int_value=4
        )
        self.assertEqual(d1.int_value, 5)
        self.assertEqual(d1.value, 12.5)
        self.assertEqual(d1.value, 12.5)
        self.assertEqual(d2.device_timestamp, 60)
        self.assertEqual(d2.value, 25.0)
        self.assertEqual(d3.int_value, 2)
        self.assertEqual(d3.value, 2.0)
        self.assertEqual(d3.device_timestamp, 120)
        self.assertEqual(d4.int_value, 4)
        self.assertEqual(d4.value, 24.0)

    def testFirehosePayload(self):
        s = StreamId.objects.create(device=self.d, variable=self.v, project=self.p, created_by=self.u)
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        t1 = dateutil.parser.parse('2016-09-28T10:01:00Z')
        t2 = dateutil.parser.parse('2016-09-28T10:02:00Z')
        helper = StreamDataBuilderHelper()
        d1 = helper.build_data_obj(
            stream_slug=s.slug,
            timestamp=t0,
            int_value=5,
            streamer_local_id=1
        )
        payload = StreamDataBuilderHelper.get_firehose_payload(d1)
        self.assertEqual(payload['int_value'], 5)
        self.assertEqual(payload['streamer_local_id'], 1)
        self.assertFalse('device_timestamp' in payload)
        d2 = helper.build_data_obj(
            stream_slug=s.slug,
            timestamp=t1,
            device_timestamp=60,
            int_value=10,
            value=0
        )
        payload = StreamDataBuilderHelper.get_firehose_payload(d2)
        self.assertEqual(payload['int_value'], 10)
        self.assertEqual(payload['value'], 10.0)
        self.assertEqual(payload['dirty_ts'], False)
        self.assertEqual(payload['status'], 'unk')
        self.assertEqual(payload['device_timestamp'], 60)
        d3 = helper.build_data_obj(
            stream_slug=s.slug,
            timestamp=t2,
            device_timestamp=120,
            int_value=0
        )
        payload = StreamDataBuilderHelper.get_firehose_payload(d3)
        self.assertEqual(payload['int_value'], 0)

    def testMdoHelper(self):
        helper = MdoHelper(2, 10, 5.0)
        value = 10
        converted_value = helper.compute(value)
        self.assertEqual(helper.compute_reverse(converted_value), value)

    def testGetStreamMdo(self):
        s = StreamId.objects.create(device=self.d, variable=self.v, project=self.p, created_by=self.u)
        self.v.multiplication_factor = 5
        self.v.var_type = self.var_type
        self.v.save()
        s.mdo_type = 'V'
        s.save()
        helper = get_stream_mdo(s)
        self.assertEqual(helper._m, 5)
        self.assertEqual(helper._d, 1)
        self.assertEqual(helper._o, 0.0)

        s.mdo_type = 'S'
        s.multiplication_factor = 3
        s.save()

        helper = get_stream_mdo(s)
        self.assertEqual(helper._m, 3)
        self.assertEqual(helper._d, 1)
        self.assertEqual(helper._o, None)


    def testGetInputStreamMdo(self):
        s = StreamId.objects.create(device=self.d, variable=self.v, project=self.p, created_by=self.u)
        self.v.multiplication_factor = 5
        self.v.var_type = self.var_type
        self.v.input_unit = self.input_unit1
        self.v.save()
        s.save()
        helper = get_stream_input_mdo(s)
        self.assertEqual(helper._m, self.input_unit1.m)
        self.assertEqual(helper._d, self.input_unit1.d)
        self.assertEqual(helper._o, 0.0)

        s.input_unit = self.input_unit2
        s.save()

        helper = get_stream_input_mdo(s)
        self.assertEqual(helper._m, self.input_unit2.m)
        self.assertEqual(helper._d, self.input_unit2.d)
        self.assertEqual(helper._o, 0.0)


    def testGetOutputStreamMdo(self):
        self.output_unit1 = VarTypeOutputUnit.objects.create(
            var_type=self.var_type,
            unit_full='Liters',
            unit_short='l',
            m=1,
            d=2,
            created_by=self.u
        )
        self.output_unit2 = VarTypeOutputUnit.objects.create(
            var_type=self.var_type,
            unit_full='Gallons',
            unit_short='g',
            m=3,
            d=4,
            created_by=self.u
        )
        s = StreamId.objects.create(device=self.d, variable=self.v, project=self.p, created_by=self.u)
        self.v.multiplication_factor = 5
        self.v.var_type = self.var_type
        self.v.output_unit = self.output_unit1
        self.v.save()
        s.save()
        helper = get_stream_output_mdo(s)
        self.assertEqual(helper._m, self.output_unit1.m)
        self.assertEqual(helper._d, self.output_unit1.d)
        self.assertEqual(helper._o, 0.0)

        s.output_unit = self.output_unit2
        s.save()

        helper = get_stream_output_mdo(s)
        self.assertEqual(helper._m, self.output_unit2.m)
        self.assertEqual(helper._d, self.output_unit2.d)
        self.assertEqual(helper._o, 0.0)







