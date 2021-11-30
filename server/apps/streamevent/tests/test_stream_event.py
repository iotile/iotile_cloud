import datetime
from unittest import mock

import dateutil.parser

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.devicetemplate.models import DeviceTemplate
from apps.org.models import Org, OrgMembership
from apps.physicaldevice.models import Device
from apps.stream.models import StreamId, StreamVariable
from apps.streamfilter.models import *
from apps.utils.gid.convert import *
from apps.utils.test_util import TestMixin
from apps.vartype.models import VarType, VarTypeInputUnit

from ..models import *

SNS_DELETE_S3 = getattr(settings, 'SNS_DELETE_S3')

user_model = get_user_model()


class StreamEventTestCase(TestMixin, TestCase):

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
            name='Var A', project=self.p, created_by=self.u, lid=0x7001,
        )
        self.d = Device.objects.create_device(id=0xa, project=self.p, label='d1', template=dt, created_by=self.u)
        self.var_type = VarType.objects.create(
            name='Accelerometer',
            storage_units_full='Object',
            created_by=self.u
        )

    def tearDown(self):
        StreamEventData.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        DeviceTemplate.objects.all().delete()
        Project.objects.all().delete()
        Org.objects.all().delete()
        OrgMembership.objects.all().delete()
        VarTypeInputUnit.objects.all().delete()
        VarType.objects.all().delete()

    def testBasicObject(self):
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        data = StreamEventData(
            timestamp=t0,
            device_timestamp=10,
            stream_slug='s--0000-0001--0000-0000-0000-0001--0001',
            streamer_local_id=1
        )
        self.assertEqual(data.incremental_id, 1)
        data.deduce_slugs_from_stream_id()
        self.assertEqual(data.project_slug, 'p--0000-0001')
        self.assertEqual(data.device_slug, 'd--0000-0000-0000-0001')
        self.assertEqual(data.variable_slug, 'v--0000-0001--0001')
        self.assertEqual(data.s3_key_path, '')
        data.set_s3_key_path()
        self.assertNotEqual(data.s3_key_path, '')
        self.assertIsNotNone(data.uuid)

    def testS3KeyPath(self):
        dt_template = getattr(settings, 'STREAM_EVENT_DATA_S3_KEY_DATETIME_FORMAT_V2')
        dt = datetime.datetime(2017, 5, 6, 7)
        s3key_path = dt.strftime(dt_template)
        self.assertEqual(s3key_path, '2017/05/06/07')
        dt = datetime.datetime(2017, 11, 16, 17)
        s3key_path = dt.strftime(dt_template)
        self.assertEqual(s3key_path, '2017/11/16/17')

    def testJsonSummary(self):
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        data = StreamEventData(
            timestamp=t0,
            device_timestamp=10,
            stream_slug='s--0000-0001--0000-0000-0000-0001--0001',
            streamer_local_id=1
        )
        self.assertIsNone(data.extra_data)
        self.assertIsNone(data.summary)
        self.assertIsNone(data.get_summary_value('Var1'))
        data.set_summary_value('Var1', 'Val1')
        data.set_summary_value('Var2', 2)
        data.set_summary_value('Var3', True)
        data.save()
        self.assertIsNotNone(data.extra_data)
        self.assertIsNotNone(data.summary)
        self.assertEqual(data.summary['Var1'], 'Val1')
        self.assertEqual(data.summary['Var2'], 2)
        self.assertEqual(data.summary['Var3'], True)
        self.assertEqual(data.get_summary_value('Var1'), 'Val1')
        self.assertEqual(data.get_summary_value('Var2'), 2)
        self.assertEqual(data.get_summary_value('Var3'), True)
        self.assertIsNone(data.get_summary_value('NotValidKey'))

    def testS3Properties(self):
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        data = StreamEventData(
            id=5,
            timestamp=t0,
            device_timestamp=10,
            stream_slug='s--0000-0001--0000-0000-0000-0001--0001',
            streamer_local_id=1
        )
        data.deduce_slugs_from_stream_id()

        # Version 1
        data.format_version = 1
        self.assertEqual(data.s3key, 'dev/s--0000-0001--0000-0000-0000-0001--0001/{}.json'.format(str(data.uuid)))
        data.stream_slug = 's--0000-0001--0002-0000-0000-0001--0001'
        self.assertEqual(data.s3key, 'dev/s--0000-0001--0000-0000-0000-0001--0001/{}.json'.format(str(data.uuid)))

        # Version 2
        data.format_version = 2
        data.set_s3_key_path()
        dt = timezone.now()
        dt_template = getattr(settings, 'STREAM_EVENT_DATA_S3_KEY_DATETIME_FORMAT_V2')
        s3key_path = dt.strftime(dt_template)
        self.assertEqual(data.s3key, 'dev/{0}/{1}.json'.format(s3key_path, str(data.uuid)))
        self.assertEqual(data.s3bucket, 'iotile-cloud-stream-event-data')

    @mock.patch("apps.streamevent.models.sns_lambda_message")
    def testDeleteS3FilePreDeleteReceiver(self, mock_sns):
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        StreamEventData.objects.create(
            timestamp=t0,
            device_timestamp=10,
            stream_slug='s--0000-0001--0000-0000-0000-0001--0001',
            streamer_local_id=1
        )
        StreamEventData.objects.create(
            timestamp=t0,
            device_timestamp=10,
            stream_slug='s--0000-0001--0000-0000-0000-0001--0001',
            streamer_local_id=2
        )
        StreamEventData.objects.create(
            timestamp=t0,
            device_timestamp=10,
            stream_slug='s--0000-0001--0000-0000-0000-0001--0001',
            streamer_local_id=3
        )
        StreamEventData.objects.create(
            timestamp=t0,
            device_timestamp=10,
            stream_slug='s--0000-0001--0000-0000-0000-0001--0001',
            streamer_local_id=4
        )

        event = StreamEventData.objects.all().first()
        event.delete()
        mock_sns.assert_called_with(SNS_DELETE_S3, [{"bucket": event.s3bucket, "key": event.s3key,
                                                     "uuid": str(event.uuid)}])

        StreamEventData.objects.filter(stream_slug='s--0000-0001--0000-0000-0000-0001--0001').delete()
        self.assertEqual(mock_sns.call_count, 4)
        self.assertEqual(StreamEventData.objects.all().count(), 0)

        StreamEventData.objects.create(
            timestamp=t0,
            device_timestamp=10,
            stream_slug='s--0000-0001--0000-0000-0000-0001--0002',
            streamer_local_id=2
        )
        StreamEventData.objects.create(
            timestamp=t0,
            device_timestamp=10,
            stream_slug='s--0000-0001--0000-0000-0000-0001--0002',
            streamer_local_id=3
        )
        StreamEventData.objects.create(
            timestamp=t0,
            device_timestamp=10,
            stream_slug='s--0000-0001--0000-0000-0000-0001--0002',
            streamer_local_id=4
        )
        self.assertEqual(StreamEventData.objects.all().count(), 3)
        StreamEventData.objects.all().delete()
        self.assertEqual(mock_sns.call_count, 7)
        self.assertEqual(StreamEventData.objects.all().count(), 0)
