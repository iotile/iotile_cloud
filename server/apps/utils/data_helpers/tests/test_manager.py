from datetime import timedelta
from unittest import mock

import dateutil.parser
from django_pandas.managers import DataFrameQuerySet

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.test import TestCase
from django.utils import timezone

from apps.physicaldevice.models import Device
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.helpers import StreamDataBuilderHelper
from apps.streamdata.models import StreamData
from apps.utils.data_helpers.manager import DataManager
from apps.utils.test_util import TestMixin


class TestDataManager(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=1,
        )
        self.v2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p2, created_by=self.u3, lid=2,
        )
        self.v3 = StreamVariable.objects.create_variable(
            name='Var C', project=self.p1, created_by=self.u2, lid=3,
        )
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)
        StreamId.objects.create_after_new_device(self.pd1)
        StreamId.objects.create_after_new_device(self.pd2)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()
        self.s2 = StreamId.objects.filter(variable=self.v2).first()
        self.s3 = StreamId.objects.filter(variable=self.v3).first()

        self.ts_now = timezone.now()
        self.sd1 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=self.ts_now + timedelta(seconds=10),
            int_value=5,
            streamer_local_id=5,
        )
        self.sd2 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=self.ts_now + timedelta(seconds=20),
            streamer_local_id=6,
            int_value=6,
        )
        self.sd3 = StreamData.objects.create(
            stream_slug=self.s1.slug,
            type='Num',
            timestamp=self.ts_now + timedelta(seconds=30),
            int_value=7,
            streamer_local_id=7,
        )
        self.sd4 = StreamData.objects.create(
            stream_slug=self.s2.slug,
            type='Num',
            timestamp=self.ts_now + timedelta(seconds=10),
            int_value=8,
            streamer_local_id=8,
        )
        self.sd5 = StreamData.objects.create(
            stream_slug=self.s2.slug,
            type='Num',
            timestamp=self.ts_now + timedelta(seconds=20),
            int_value=9,
            streamer_local_id=9,
        )
        self.sd6 = StreamData.objects.create(
            stream_slug=self.s3.slug,
            type='Num',
            timestamp=self.ts_now + timedelta(seconds=10),
            int_value=10,
            streamer_local_id=10,
        )

    def tearDown(self):
        StreamData.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    @mock.patch('apps.streamdata.models.StreamDataManager.filter')
    def testValidateFilterQ(self, mock_filter):
        q = Q(
            device_slug='valid',
            device_slug__in=['valid'],
            project_slug='valid',
            stream_slug='valid',
        )
        DataManager.filter_qs_using_q('data', q)

        q |= Q(stream_slug__in=['also', 'valid'])
        DataManager.filter_qs_using_q('data', q)

        q |= Q(timestamp__lt='valid', id__in=['this', 'is', 'valid'])
        DataManager.filter_qs_using_q('data', q)

        q &= Q(timestamp__gt=timezone.now(), timestamp__lte='valid')
        DataManager.filter_qs_using_q('data', q)

        q |= Q(timestamp__gt='') & (~q | Q(timestamp__gte='valid', timestamp__lt=timezone.now()))
        DataManager.filter_qs_using_q('data', q)

        q = ~q | Q(device_slug='valid', dirty_ts=True, int_value=42)
        with self.assertRaises(AssertionError):
            DataManager.filter_qs_using_q('data', q)
        DataManager.filter_qs_using_q('data', q, extras=['int_value'])

        q |= Q(int_value__in=[1, 2, 3], project_slug__in=['valid'], streamer_local_id=42)
        with self.assertRaises(AssertionError):
            DataManager.filter_qs_using_q('data', q)
        DataManager.filter_qs_using_q('data', q, extras=['int_value', 'int_value__in'])

        q &= Q(streamer_local_id__gt=0, streamer_local_id__lt=42)
        with self.assertRaises(AssertionError):
            DataManager.filter_qs_using_q('data', q)
        DataManager.filter_qs_using_q('data', q, extras=['int_value', 'int_value__in'])

        q &= Q(streamer_local_id__gte=0, streamer_local_id__lte=42)
        with self.assertRaises(AssertionError):
            DataManager.filter_qs_using_q('data', q)
        DataManager.filter_qs_using_q('data', q, extras=['int_value', 'int_value__in'])

        q = Q(
            variable_slug='valid',
            variable_slug__contains='valid',
            variable_slug__icontains='valid',
            variable_slug__endswith='valid',
            streamer_local_id__in=[1, 2, 3],
        )
        DataManager.filter_qs_using_q('data', q)

        q = q | (~q & Q(arg_doesnt_exist=''))
        with self.assertRaises(AssertionError):
            DataManager.filter_qs_using_q('data', q)
        q = Q(
            timestamp__gte=timezone.now(),
            timestamp__lte=timezone.now(),
        )
        DataManager.filter_qs_using_q('data', q)
        q &= Q(stream_slug__in='invalid type')
        with self.assertRaises(AssertionError):
            DataManager.filter_qs_using_q('data', q)

    @mock.patch('apps.streamdata.models.StreamDataManager.filter')
    def testValidateFilterKwargs(self, mock_filter):
        DataManager.filter_qs(
            'data',
            device_slug='valid',
            device_slug__in=['valid'],
            id__in=['this', 'is', 'valid'],
            project_slug='valid',
            stream_slug='valid',
            stream_slug__in=['also', 'valid'],
            timestamp__gte='',
            timestamp__lt=timezone.now(),
            timestamp__gt=timezone.now(),
            timestamp__lte='valid',
            dirty_ts=True,
            project_slug__in=['valid'],
            streamer_local_id=42,
            streamer_local_id__gt=0,
            streamer_local_id__lt=42,
            streamer_local_id__gte=0,
            streamer_local_id__lte=42,
            variable_slug='valid',
            variable_slug__contains='valid',
            variable_slug__icontains='valid',
            variable_slug__endswith='valid',
            streamer_local_id__in=[1, 2, 3],
            extras={
                'int_value': 42,
                'int_value__in': [1, 2, 3],
            },
        )
        DataManager.filter_qs(
            'data',
            timestamp__lt='valid',
            timestamp__gte=timezone.now(),
            timestamp__lte=timezone.now(),
            timestamp__gt='valid',
        )
        with self.assertRaises(AssertionError):
            DataManager.filter_qs('data', arg_doesnt_exist='')
        with self.assertRaises(AssertionError):
            DataManager.filter_qs('data', stream_slug__in='invalid type')
        with self.assertRaises(AssertionError):
            DataManager.filter_qs('data', int_value__in=['extra', 'arg'])
        with self.assertRaises(AssertionError):
            DataManager.filter_qs('data', extras={'arg_doesnt_exist': ''})
        with self.assertRaises(AssertionError):
            DataManager.filter_qs('data', extras={'stream_slug__in': 'invalid type'})

    @mock.patch('apps.streamdata.models.StreamDataManager.get')
    def testValidateGetKwargs(self, mock_get):
        DataManager.get(
            'data',
            device_slug='valid',
            streamer_local_id=42,
        )
        DataManager.get(
            'event',
            extras={
                'uuid': 'valid extra',
            },
        )
        with self.assertRaises(AssertionError):
            DataManager.get('data', arg_doesnt_exist='')
        with self.assertRaises(AssertionError):
            DataManager.get('data', streamer_local_id='invalid type')
        with self.assertRaises(AssertionError):
            DataManager.get('data', extras={'arg_doesnt_exist': ''})
        with self.assertRaises(AssertionError):
            DataManager.get('data', extras={'streamer_local_id': 'invalid type'})

    def testValidateBuildKwargs(self):
        DataManager.build(
            'event',
            device_timestamp=42,
            status='cln',
            stream_slug='valid',
            streamer_local_id=42,
            timestamp=timezone.now(),
            extras={
                'extra_data': {'some': 'extra', 'data': [1, 2, 3]},
            },
        )

        DataManager.build(
            'data',
            device_timestamp=42,
            status='cln',
            stream_slug='valid',
            streamer_local_id=42,
            timestamp=timezone.now(),
            extras={
                'type': 'Num',
                'value': 12.0,
                'int_value': 12
            },
        )
        with self.assertRaises(AssertionError):
            DataManager.build('event', arg_doesnt_exist='')
        with self.assertRaises(AssertionError):
            DataManager.build('event', streamer_local_id='invalid type')
        with self.assertRaises(AssertionError):
            DataManager.build('data', extras={'arg_doesnt_exist': ''})
        with self.assertRaises(AssertionError):
            DataManager.build('data', extras={'streamer_local_id': 'invalid type'})

    def testFilterQs(self):
        self.assertEqual(DataManager.filter_qs('data', stream_slug__in=[self.s1.slug, self.s2.slug]).count(), 5)
        self.assertEqual(DataManager.filter_qs('data', stream_slug=self.s1.slug).count(), 3)
        self.assertEqual(DataManager.filter_qs('data', project_slug=self.p2.slug).count(), 2)
        self.assertEqual(DataManager.filter_qs('data', device_slug=self.pd1.slug).count(), 4)
        self.assertEqual(DataManager.filter_qs('data', timestamp__gte=str(self.ts_now), timestamp__lt=self.ts_now + timedelta(seconds=20)).count(), 3)
        self.assertEqual(DataManager.filter_qs('data', timestamp__gt=self.ts_now, timestamp__lte=str(self.ts_now + timedelta(seconds=20))).count(), 5)
        self.assertEqual(DataManager.filter_qs('data', stream_slug=self.s1.slug, timestamp__lt=self.ts_now).count(), 0)
        self.assertEqual(DataManager.filter_qs('data', id__in=[self.sd2.id, self.sd5.id, self.sd6.id]).count(), 3)
        self.assertEqual(DataManager.filter_qs('data', extras={'int_value__in': [3, 6, 8]}).count(), 2)

    def testFilterQsUsingQ(self):
        q = Q(stream_slug__in=[self.s1.slug, self.s2.slug])
        self.assertEqual(DataManager.filter_qs_using_q('data', q).count(), 5)
        self.assertEqual(DataManager.filter_qs_using_q('data', ~q).count(), 1)

        q = Q(stream_slug=self.s1.slug)
        self.assertEqual(DataManager.filter_qs_using_q('data', q).count(), 3)
        self.assertEqual(DataManager.filter_qs_using_q('data', ~q).count(), 3)

        q = Q(project_slug=self.p2.slug)
        self.assertEqual(DataManager.filter_qs_using_q('data', q).count(), 2)
        self.assertEqual(DataManager.filter_qs_using_q('data', ~q).count(), 4)

        q = Q(id__in=[self.sd2.id, self.sd5.id, self.sd6.id])
        self.assertEqual(DataManager.filter_qs_using_q('data', q).count(), 3)
        self.assertEqual(DataManager.filter_qs_using_q('data', ~q).count(), 3)

        q = Q(int_value__in=[3, 6, 8])
        self.assertEqual(DataManager.filter_qs_using_q('data', q, extras=['int_value__in']).count(), 2)
        self.assertEqual(DataManager.filter_qs_using_q('data', ~q, extras=['int_value__in']).count(), 4)

        q = Q(device_slug=self.pd1.slug)
        self.assertEqual(DataManager.filter_qs_using_q('data', q).count(), 4)
        self.assertEqual(DataManager.filter_qs_using_q('data', q & ~q).count(), 0)

        q = Q(timestamp__gte=str(self.ts_now), timestamp__lt=self.ts_now + timedelta(seconds=20))
        self.assertEqual(DataManager.filter_qs_using_q('data', q).count(), 3)
        self.assertEqual(DataManager.filter_qs_using_q('data', q & ~q).count(), 0)

        q = Q(timestamp__gt=self.ts_now, timestamp__lte=str(self.ts_now + timedelta(seconds=20)))
        self.assertEqual(DataManager.filter_qs_using_q('data', q).count(), 5)
        self.assertEqual(DataManager.filter_qs_using_q('data', q | ~q).count(), 6)

        q = Q(stream_slug=self.s1.slug, timestamp__lt=self.ts_now)
        self.assertEqual(DataManager.filter_qs_using_q('data', q).count(), 0)
        self.assertEqual(DataManager.filter_qs_using_q('data', q | ~q).count(), 6)

        q = Q(stream_slug=self.s3.slug) | (Q(project_slug=self.p2.slug) & Q(timestamp__gte=self.ts_now + timedelta(seconds=20)))
        self.assertEqual(DataManager.filter_qs_using_q('data', q).count(), 2)
        self.assertEqual(DataManager.filter_qs_using_q('data', ~q).count(), 4)
        self.assertEqual(DataManager.filter_qs_using_q('data', q | ~q).count(), 6)
        self.assertEqual(DataManager.filter_qs_using_q('data', q & ~q).count(), 0)

    def testDfFilterGsUsingQ(self):
        q = Q(stream_slug__in=[self.s1.slug, self.s2.slug])
        qs = DataManager.df_filter_qs_using_q('data', q)
        self.assertEqual(qs.count(), 5)
        self.assertTrue(isinstance(qs, DataFrameQuerySet))

    def testGet(self):
        self.assertEqual(DataManager.get('data', device_slug=self.pd1.slug, streamer_local_id=5), self.sd1)
        self.assertEqual(DataManager.get('data', device_slug=self.pd2.slug, streamer_local_id=8), self.sd4)
        self.assertEqual(DataManager.get('data', device_slug=self.pd1.slug, streamer_local_id=10), self.sd6)
        with self.assertRaises(ObjectDoesNotExist):
            DataManager.get('data', device_slug=self.pd1.slug, streamer_local_id=4)

    def testAllQs(self):
        all_qs = DataManager.all_qs('data')
        self.assertEqual(all_qs.count(), 6)
        self.assertTrue(self.sd1 in all_qs)
        self.assertTrue(self.sd2 in all_qs)
        self.assertTrue(self.sd3 in all_qs)
        self.assertTrue(self.sd4 in all_qs)
        self.assertTrue(self.sd5 in all_qs)
        self.assertTrue(self.sd6 in all_qs)

        StreamData.objects.filter(stream_slug=self.s1).delete()
        all_qs = DataManager.all_qs('data')
        self.assertEqual(all_qs.count(), 3)
        self.assertFalse(self.sd1 in all_qs)
        self.assertFalse(self.sd2 in all_qs)
        self.assertFalse(self.sd3 in all_qs)
        self.assertTrue(self.sd4 in all_qs)
        self.assertTrue(self.sd5 in all_qs)
        self.assertTrue(self.sd6 in all_qs)

    def testNoneQs(self):
        self.assertEqual(DataManager.none_qs('data').count(), 0)
        self.assertEqual(DataManager.none_qs('event').count(), 0)

    def testCount(self):
        self.assertEqual(DataManager.count('data'), 6)
        StreamData.objects.filter(stream_slug=self.s1).delete()
        self.assertEqual(DataManager.count('data'), 3)

    def testIsInstance(self):
        self.assertTrue(DataManager.is_instance('data', self.sd1))
        self.assertFalse(DataManager.is_instance('event', self.sd1))

    def testBuild(self):
        self.assertEqual(StreamData.objects.count(), 6)
        self.assertEqual(StreamData.objects.filter(stream_slug=self.s1.slug).count(), 3)
        sd = DataManager.build(
            'data',
            stream_slug=self.s1.slug,
            timestamp=timezone.now(),
            streamer_local_id=4,
        )
        self.assertTrue(isinstance(sd, StreamData))
        sd.save()
        self.assertEqual(StreamData.objects.count(), 7)
        self.assertEqual(StreamData.objects.filter(stream_slug=self.s1.slug).count(), 4)
        self.assertEqual(StreamData.objects.first().streamer_local_id, 4)

    def testBulkCreate(self):
        self.assertEqual(StreamData.objects.all().count(), 6)

        payload = []
        helper = StreamDataBuilderHelper()
        for i in range(10):
            stream_data = helper.build_data_obj(
                stream_slug=self.s3.slug,
                timestamp=self.ts_now + timedelta(seconds=1000 + i * 10),
                int_value=100 + i,
            )
            payload.append(stream_data)
        DataManager.bulk_create('data', payload)

        self.assertEqual(StreamData.objects.all().count(), 16)
        self.assertEqual(StreamData.objects.filter(stream_slug=self.s3.slug).count(), 11)
        self.assertEqual(StreamData.objects.filter(timestamp__gte=self.ts_now + timedelta(seconds=1000)).count(), 10)
        self.assertEqual(StreamData.objects.filter(int_value__gte=100).count(), 10)

    def testSave(self):
        self.assertEqual(StreamData.objects.all().count(), 6)
        new_data = StreamData(
            stream_slug=self.s1.slug,
            timestamp=timezone.now(),
            streamer_local_id=4,
            int_value=4,
        )
        with self.assertRaises(AssertionError):
            DataManager.save('event', new_data)
        DataManager.save('data', new_data)
        self.assertEqual(StreamData.objects.all().count(), 7)

    def testFirehosePayload(self):
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        t1 = dateutil.parser.parse('2016-09-28T10:01:00Z')
        t2 = dateutil.parser.parse('2016-09-28T10:02:00Z')
        helper = StreamDataBuilderHelper()
        d1 = helper.build_data_obj(
            stream_slug=self.s1.slug,
            timestamp=t0,
            int_value=5,
            streamer_local_id=1
        )
        payload = DataManager._get_firehose_payload(d1)
        self.assertEqual(payload['int_value'], 5)
        self.assertEqual(payload['streamer_local_id'], 1)
        self.assertFalse('device_timestamp' in payload)
        d2 = helper.build_data_obj(
            stream_slug=self.s1.slug,
            timestamp=t1,
            device_timestamp=60,
            int_value=10,
            value=0
        )
        payload = DataManager._get_firehose_payload(d2)
        self.assertEqual(payload['int_value'], 10)
        self.assertEqual(payload['value'], 10.0)
        self.assertEqual(payload['dirty_ts'], False)
        self.assertEqual(payload['status'], 'unk')
        self.assertEqual(payload['device_timestamp'], 60)
        d3 = helper.build_data_obj(
            stream_slug=self.s1.slug,
            timestamp=t2,
            device_timestamp=120,
            int_value=0
        )
        payload = DataManager._get_firehose_payload(d3)
        self.assertEqual(payload['int_value'], 0)
