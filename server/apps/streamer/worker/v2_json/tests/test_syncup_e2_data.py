import json
import os
import dateutil.parser
from unittest import mock

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils.dateparse import parse_datetime

from apps.utils.test_util import TestMixin
from apps.streamdata.models import StreamData
from apps.streamdata.helpers import StreamDataBuilderHelper
from apps.streamevent.models import StreamEventData
from apps.streamevent.helpers import StreamEventDataBuilderHelper
from apps.stream.models import StreamVariable, StreamId
from apps.utils.timezone_utils import *
from apps.streamer.serializers import *
from apps.sensorgraph.models import SensorGraph

from ...common.test_utils import *
from ..syncup_e2_data import SyncUpE2DataAction

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')

class SynupE2DataTestCase(TestMixin, TestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=0x5020,
        )
        self.sg = SensorGraph.objects.create_graph(name='SG1', report_processing_engine_ver=100,
                                                   created_by=self.u2, org=self.o1)
        self.pd1 = Device.objects.create_device(id=0xa, project=self.p1, sg=self.sg, label='d1',
                                                template=self.dt1, created_by=self.u2)
        StreamId.objects.create_after_new_device(self.pd1)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()

    def tearDown(self):
        StreamData.objects.all().delete()
        StreamEventData.objects.all().delete()
        Streamer.objects.all().delete()
        StreamerReport.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasicE2SyncUp(self):

        self.s1.data_type = 'E2'
        self.s1.save()

        data_helper = StreamDataBuilderHelper()

        data_entries = []
        data_entries.append(data_helper.build_data_obj(
            stream_slug=self.s1.slug,
            streamer_local_id=10,
            timestamp=parse_datetime("2017-01-10T10:00:00Z"),
            int_value=1
        ))
        data_entries.append(data_helper.build_data_obj(
            stream_slug=self.s1.slug,
            streamer_local_id=20,
            timestamp=parse_datetime("2017-01-10T10:00:10Z"),
            int_value=2
        ))
        data_entries.append(data_helper.build_data_obj(
            stream_slug=self.s1.slug,
            streamer_local_id=30,
            timestamp=parse_datetime("2017-01-10T10:00:20Z"),
            int_value=3
        ))

        StreamData.objects.bulk_create(data_entries)
        self.assertEqual(StreamData.objects.count(), 3)

        event_helper = StreamEventDataBuilderHelper()

        event_entries = []
        event_entries.append(event_helper.process_serializer_data({
            "stream_slug": self.s1.slug,
            "timestamp": "2018-01-20T00:00:00Z",
            "streamer_local_id": 2,
            "extra_data": {}
        }))
        event_entries.append(event_helper.process_serializer_data({
            "stream_slug": self.s1.slug,
            "timestamp": "2018-01-20T01:12:00Z",
            "streamer_local_id": 3,
            "extra_data": {}
        }))

        StreamEventData.objects.bulk_create(event_entries)
        self.assertEqual(StreamEventData.objects.count(), 2)

        action = SyncUpE2DataAction()

        action.execute({
            'stream_slug': self.s1.slug,
            'seq_ids': [2, 3],
            'attempt_count': 5
        })

        e1 = StreamEventData.objects.first()
        self.assertEqual(e1.timestamp, parse_datetime("2017-01-10T10:00:10Z"))
        e2 = StreamEventData.objects.last()
        self.assertEqual(e2.timestamp, parse_datetime("2017-01-10T10:00:20Z"))

    @mock.patch('apps.streamer.worker.v2_json.syncup_e2_data.SyncUpE2DataAction.schedule')
    def testIncompleteE2SyncUp(self, mock_schedule):

        self.s1.data_type = 'E2'
        self.s1.save()

        data_helper = StreamDataBuilderHelper()

        data_entries = []
        data_entries.append(data_helper.build_data_obj(
            stream_slug=self.s1.slug,
            streamer_local_id=10,
            timestamp=parse_datetime("2017-01-10T10:00:00Z"),
            int_value=1
        ))
        data_entries.append(data_helper.build_data_obj(
            stream_slug=self.s1.slug,
            streamer_local_id=20,
            timestamp=parse_datetime("2017-01-10T10:00:10Z"),
            int_value=2
        ))

        StreamData.objects.bulk_create(data_entries)
        self.assertEqual(StreamData.objects.count(), 2)

        event_helper = StreamEventDataBuilderHelper()

        event_entries = []
        event_entries.append(event_helper.process_serializer_data({
            "stream_slug": self.s1.slug,
            "timestamp": "2018-01-20T00:00:00Z",
            "streamer_local_id": 2,
            "extra_data": {}
        }))
        event_entries.append(event_helper.process_serializer_data({
            "stream_slug": self.s1.slug,
            "timestamp": "2018-01-20T01:12:00Z",
            "streamer_local_id": 3,
            "extra_data": {}
        }))

        StreamEventData.objects.bulk_create(event_entries)
        self.assertEqual(StreamEventData.objects.count(), 2)

        action = SyncUpE2DataAction()

        args = {
            'stream_slug': self.s1.slug,
            'seq_ids': [2, 3],
            'attempt_count': 5
        }
        action.execute(args)
        args['seq_ids'] = [3]
        args['attempt_count'] = 4
        mock_schedule.assert_called_with(args=args, delay_seconds=900)

        e1 = StreamEventData.objects.first()
        self.assertEqual(e1.timestamp, parse_datetime("2017-01-10T10:00:10Z"))
        e2 = StreamEventData.objects.last()
        self.assertEqual(e2.timestamp, parse_datetime("2018-01-20T01:12:00Z"))

    def testNoSyncUpIfE3(self):

        self.s1.data_type = 'E3'
        self.s1.save()

        data_helper = StreamDataBuilderHelper()

        data_entries = []
        data_entries.append(data_helper.build_data_obj(
            stream_slug=self.s1.slug,
            streamer_local_id=10,
            timestamp=parse_datetime("2017-01-10T10:00:00Z"),
            int_value=1
        ))
        data_entries.append(data_helper.build_data_obj(
            stream_slug=self.s1.slug,
            streamer_local_id=20,
            timestamp=parse_datetime("2017-01-10T10:00:10Z"),
            int_value=2
        ))

        StreamData.objects.bulk_create(data_entries)
        self.assertEqual(StreamData.objects.count(), 2)

        event_helper = StreamEventDataBuilderHelper()

        event_entries = []
        event_entries.append(event_helper.process_serializer_data({
            "stream_slug": self.s1.slug,
            "timestamp": "2018-01-20T00:00:00Z",
            "streamer_local_id": 2,
            "extra_data": {}
        }))
        event_entries.append(event_helper.process_serializer_data({
            "stream_slug": self.s1.slug,
            "timestamp": "2018-01-20T01:12:00Z",
            "streamer_local_id": 3,
            "extra_data": {}
        }))

        StreamEventData.objects.bulk_create(event_entries)
        self.assertEqual(StreamEventData.objects.count(), 2)

        action = SyncUpE2DataAction()

        args = {
            'stream_slug': self.s1.slug,
            'seq_ids': [2, 3],
            'attempt_count': 5
        }
        action.execute(args)
        args['seq_ids'] = [3]
        args['attempt_count'] = 4

        e1 = StreamEventData.objects.first()
        self.assertEqual(e1.timestamp, parse_datetime("2018-01-20T00:00:00Z"))
        e2 = StreamEventData.objects.last()
        self.assertEqual(e2.timestamp, parse_datetime("2018-01-20T01:12:00Z"))
