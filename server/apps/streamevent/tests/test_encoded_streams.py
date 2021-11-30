import datetime
from unittest import mock

import dateutil.parser

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.devicetemplate.models import DeviceTemplate
from apps.org.models import Org, OrgMembership
from apps.physicaldevice.models import Device
from apps.stream.models import StreamId
from apps.streamdata.helpers import StreamDataBuilderHelper
from apps.streamdata.models import StreamData
from apps.streamfilter.models import *
from apps.utils.gid.convert import *
from apps.utils.iotile.variable import ENCODED_STREAM_VALUES
from apps.utils.test_util import TestMixin
from apps.vartype.models import VarType, VarTypeDecoder, VarTypeInputUnit

from ..helpers import EncodedStreamToEventDataHelper
from ..models import *

SNS_DELETE_S3 = getattr(settings, 'SNS_DELETE_S3')

user_model = get_user_model()


class EncodedStreamHelperTestCase(TestMixin, TestCase):

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
            name='Var A', project=self.p, created_by=self.u, lid=0x5020,
        )
        self.d = Device.objects.create_device(id=0xa, project=self.p, label='d1', template=dt, created_by=self.u)

    def tearDown(self):
        StreamData.objects.all().delete()
        StreamEventData.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        DeviceTemplate.objects.all().delete()
        Project.objects.all().delete()
        Org.objects.all().delete()
        OrgMembership.objects.all().delete()
        VarTypeInputUnit.objects.all().delete()
        VarTypeDecoder.objects.all().delete()
        VarType.objects.all().delete()

    def _add_dummy_data(self, stream, ts, dts, sigid, data):
        helper = StreamDataBuilderHelper()
        result = []

        result.append(helper.build_data_obj(
            stream_slug=stream.slug,
            type='Num',
            device_timestamp=dts,
            streamer_local_id=sigid,
            timestamp=ts,
            int_value=ENCODED_STREAM_VALUES['BEGIN']
        ))
        sigid += 1
        for item in data:
            result.append(helper.build_data_obj(
                stream_slug=stream.slug,
                type='Num',
                device_timestamp=dts,
                streamer_local_id=sigid,
                timestamp=ts,
                int_value=item
            ))
            sigid += 1

        result.append(helper.build_data_obj(
            stream_slug=stream.slug,
            type='Num',
            device_timestamp=dts,
            streamer_local_id=sigid,
            timestamp=ts,
            int_value=ENCODED_STREAM_VALUES['END']
        ))
        sigid += 1

        return result

    def testBasicObject(self):
        var_type = VarType.objects.create(
            name='Accelerometer',
            storage_units_full='Encoded',
            created_by=self.u
        )
        VarTypeDecoder.objects.create(var_type=var_type, created_by=self.u,
                                      raw_packet_format='<LL',
                                      packet_info={
                                          'decoding': [
                                              "l{k1}",
                                              "H{k2}",
                                              "h{k3}",
                                          ]
                                        })
        self.assertIsNotNone(var_type.decoder)
        s1 = StreamId.objects.create(device=self.d, variable=self.v, project=self.p, var_type=var_type,
                                     created_by=self.u, mdo_type = 'V')

        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        data_stream = self._add_dummy_data(stream=s1, ts=t0, dts=20, sigid=5, data=[0xFFFFFFFB, 0x00020001])
        self.assertEqual(len(data_stream), 4)

        helper = EncodedStreamToEventDataHelper(s1)
        for point in data_stream[0:3]:
            event = helper.process_data_point(point)
            self.assertIsNone(event)

        event = helper.process_data_point(data_stream[3])
        self.assertIsNotNone(event)
        self.assertEqual(event.extra_data['k1'], -5)
        self.assertEqual(event.extra_data['k2'], 1)
        self.assertEqual(event.extra_data['k3'], 2)
        self.assertEqual(event.stream_slug, s1.slug)
        self.assertEqual(event.incremental_id, 5)
        self.assertEqual(event.device_timestamp, 20)

        t1 = dateutil.parser.parse('2016-09-28T10:01:00Z')
        data_stream = self._add_dummy_data(stream=s1, ts=t1, dts=80, sigid=9, data=[0xFFFFFFFB, 0xFFFB0001])

        for point in data_stream[0:3]:
            event = helper.process_data_point(point)
            self.assertIsNone(event)

        event = helper.process_data_point(data_stream[3])
        self.assertIsNotNone(event)
        self.assertEqual(event.extra_data['k1'], -5)
        self.assertEqual(event.extra_data['k2'], 1)
        self.assertEqual(event.extra_data['k3'], -5)
        self.assertEqual(event.incremental_id, 9)
        self.assertEqual(event.device_timestamp, 80)

    def testExceptionHandling(self):
        var_type = VarType.objects.create(
            name='Accelerometer',
            storage_units_full='Encoded',
            created_by=self.u
        )
        VarTypeDecoder.objects.create(var_type=var_type, created_by=self.u,
                                      raw_packet_format='<LL',
                                      packet_info={
                                          'decoding': [
                                              "l{k1}",
                                              "H{k2}",
                                              "h{k3}",
                                          ]
                                        })
        self.assertIsNotNone(var_type.decoder)
        s1 = StreamId.objects.create(device=self.d, variable=self.v, project=self.p, var_type=var_type,
                                     created_by=self.u, mdo_type = 'V')

        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        data_stream = self._add_dummy_data(stream=s1, ts=t0, dts=20, sigid=5, data=[0xFFFFFFFB, 0x00020001])
        self.assertEqual(len(data_stream), 4)

        helper = EncodedStreamToEventDataHelper(s1)
        for point in data_stream[0:3]:
            event = helper.process_data_point(point)
            self.assertIsNone(event)

        event = helper.process_data_point(data_stream[3])
        self.assertIsNotNone(event)
        self.assertFalse('error' in event.extra_data)

        t1 = dateutil.parser.parse('2016-09-28T10:01:00Z')
        # Incorrect packet size. Should ignore this event
        data_stream = self._add_dummy_data(stream=s1, ts=t1, dts=80, sigid=9, data=[0xFFFB0001, 5, 0xFFFB0001])

        for point in data_stream[0:4]:
            event = helper.process_data_point(point)
            self.assertIsNone(event)

        event = helper.process_data_point(data_stream[4])
        self.assertIsNotNone(event)
        self.assertTrue('error' in event.extra_data)
        err_msg = '{}: RawPacketFromat length (<LL=3 - 1) is not the same as packet size (3)'.format(s1.slug)
        self.assertEqual(event.extra_data['error'], err_msg)
        self.assertTrue('start' in event.extra_data)
        self.assertTrue('end' in event.extra_data)
        self.assertEqual(event.extra_data['start'], 9)
        self.assertEqual(event.extra_data['end'], 13)

        t1 = dateutil.parser.parse('2016-09-28T10:01:00Z')
        # Incorrect packet size. Should ignore this event
        data_stream = self._add_dummy_data(stream=s1, ts=t1, dts=90, sigid=25, data=[0xFFFB0001, 0xFFFB0001])

        for point in data_stream[0:3]:
            event = helper.process_data_point(point)
            self.assertIsNone(event)

        event = helper.process_data_point(data_stream[3])
        self.assertIsNotNone(event)
        self.assertFalse('error' in event.extra_data)

    def testBitEncoding(self):
        var_type = VarType.objects.create(
            name='Accelerometer',
            storage_units_full='Encoded',
            created_by=self.u
        )
        VarTypeDecoder.objects.create(var_type=var_type, created_by=self.u,
                                      raw_packet_format='<LLLL',
                                      packet_info={
                                          'decoding': [
                                              "H{axis:2,peak:14}",
                                              "H{duration}",
                                              "l{delta_v_x}",
                                              "l{delta_v_y}",
                                              "l{delta_v_z}",
                                          ]
                                        })
        self.assertIsNotNone(var_type.decoder)
        s1 = StreamId.objects.create(device=self.d, variable=self.v, project=self.p, var_type=var_type,
                                     created_by=self.u, mdo_type = 'V')

        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        data = [0x05000026, 0xFFFFFFFB, 0x20, 0x5]
        data_stream = self._add_dummy_data(stream=s1, ts=t0, dts=20, sigid=5, data=data)
        self.assertEqual(len(data_stream), 6)

        helper = EncodedStreamToEventDataHelper(s1)
        for point in data_stream[0:5]:
            event = helper.process_data_point(point)
            self.assertIsNone(event)

        event = helper.process_data_point(data_stream[5])
        self.assertIsNotNone(event)
        self.assertEqual(event.extra_data['axis'], 2)
        self.assertEqual(event.extra_data['peak'], 9)
        self.assertEqual(event.extra_data['duration'], 0x500)
        self.assertEqual(event.extra_data['delta_v_x'], -5)
        self.assertEqual(event.extra_data['delta_v_y'], 0x20)
        self.assertEqual(event.extra_data['delta_v_z'], 5)

    def testEncodingMdo(self):
        var_type = VarType.objects.create(
            name='Accelerometer',
            storage_units_full='Encoded',
            created_by=self.u
        )
        VarTypeDecoder.objects.create(var_type=var_type, created_by=self.u,
                                      raw_packet_format='<LLLL',
                                      packet_info={
                                          'decoding': [
                                              "H{axis:2,peak:14}",
                                              "H{duration}",
                                              "l{delta_v_x}",
                                              "l{delta_v_y}",
                                              "l{delta_v_z}",
                                          ],
                                          "transform": {
                                              "axis": {
                                                  "map": {
                                                      "0": "x",
                                                      "1": "y",
                                                      "2": "z"
                                                  }
                                              },
                                              "peak": {
                                                  "mdo": [49, 1000, 0.0]
                                              },
                                              "delta_v_x": {
                                                  "mdo": [1, 65536, 0.0]
                                              },
                                              "delta_v_y": {
                                                  "mdo": [1, 65536, 0.0]
                                              },
                                              "delta_v_z": {
                                                  "mdo": [1, 65536, 0.0]
                                              }
                                          }
                                      })
        self.assertIsNotNone(var_type.decoder)
        s1 = StreamId.objects.create(device=self.d, variable=self.v, project=self.p, var_type=var_type,
                                     created_by=self.u, mdo_type = 'V')

        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        data = [0x05000026, 0xFFFFFFFB, 0x20, 0x5]
        data_stream = self._add_dummy_data(stream=s1, ts=t0, dts=20, sigid=5, data=data)
        self.assertEqual(len(data_stream), 6)

        helper = EncodedStreamToEventDataHelper(s1)
        for point in data_stream[0:5]:
            event = helper.process_data_point(point)
            self.assertIsNone(event)

        event = helper.process_data_point(data_stream[5])
        self.assertIsNotNone(event)
        self.assertEqual(event.extra_data['axis'], 'z')
        self.assertEqual(event.extra_data['peak'], 9 * 49 / 1000)
        self.assertEqual(event.extra_data['duration'], 0x500)
        self.assertEqual(event.extra_data['delta_v_x'], -5 / 65536)
        self.assertEqual(event.extra_data['delta_v_y'], 0x20 / 65536)
        self.assertEqual(event.extra_data['delta_v_z'], 5 / 65536)

    def testEndNoStart(self):
        # TODO: Remove this test when firmware is fixed
        var_type = VarType.objects.create(
            name='Accelerometer',
            storage_units_full='Encoded',
            created_by=self.u
        )
        VarTypeDecoder.objects.create(var_type=var_type, created_by=self.u,
                                      raw_packet_format='<LL',
                                      packet_info={
                                          'decoding': [
                                              "l{k1}",
                                              "H{k2}",
                                              "h{k3}",
                                          ]
                                        })
        self.assertIsNotNone(var_type.decoder)
        s1 = StreamId.objects.create(device=self.d, variable=self.v, project=self.p, var_type=var_type,
                                     created_by=self.u, mdo_type = 'V')

        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        helper = StreamDataBuilderHelper()
        data_stream = []

        sigid = 1
        data = [0xFFFFFFFB, 0x00020001]
        ts = t0
        dts = 20
        for item in data:
            data_stream.append(helper.build_data_obj(
                stream_slug=s1.slug,
                type='Num',
                device_timestamp=dts,
                streamer_local_id=sigid,
                timestamp=ts,
                int_value=item
            ))
            sigid += 1

        data_stream.append(helper.build_data_obj(
            stream_slug=s1.slug,
            type='Num',
            device_timestamp=dts,
            streamer_local_id=sigid,
            timestamp=ts,
            int_value=ENCODED_STREAM_VALUES['END']
        ))
        self.assertEqual(len(data_stream), 3)

        helper = EncodedStreamToEventDataHelper(s1)
        for point in data_stream[0:2]:
            event = helper.process_data_point(point)
            self.assertIsNone(event)

        event = helper.process_data_point(data_stream[2])
        self.assertIsNone(event)



