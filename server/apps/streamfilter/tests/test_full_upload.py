import json
import os
import dateutil.parser
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.utils.test_util import TestMixin
from apps.stream.models import StreamVariable, StreamId
from apps.streamdata.models import StreamData
from apps.physicaldevice.models import Device
from apps.sensorgraph.models import SensorGraph
from apps.utils.timezone_utils import *
from unittest import skipIf, mock
from apps.streamer.models import *
from apps.streamer.serializers import *
from apps.streamer.report.parser import ReportParser

from ..models import *

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')


class StreamerAPITestCase(TestMixin, APITestCase):

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
        self.sg = SensorGraph.objects.create_graph(name='SG1', report_processing_engine_ver=0,
                                                   created_by=self.u2, org=self.o1)
        self.pd1 = Device.objects.create_device(id=0xa, project=self.p1, sg=self.sg, label='d1',
                                                template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(id=0xb, project=self.p2, sg=self.sg, label='d2',
                                                template=self.dt1, created_by=self.u3)
        StreamId.objects.create_after_new_device(self.pd1)
        StreamId.objects.create_after_new_device(self.pd2)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()
        self.s2 = StreamId.objects.filter(variable=self.v2).first()
        self.out_var1 = StreamVariable.objects.create_variable(
            name='Derived 1', project=self.p1, created_by=self.u2, lid=3,
        )
        self.out_var2 = StreamVariable.objects.create_variable(
            name='Derived 2', project=self.p1, created_by=self.u2, lid=4,
        )
        self.out_var3 = StreamVariable.objects.create_variable(
            name='Derived 3', project=self.p1, created_by=self.u2, lid=5,
        )
        self.out_stream1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.out_var1, device=self.pd1, created_by=self.u2
        )
        self.out_stream2 = StreamId.objects.create_stream(
            project=self.p1, variable=self.out_var2, device=self.pd1, created_by=self.u2
        )
        self.out_stream3 = StreamId.objects.create_stream(
            project=self.p1, variable=self.out_var3, device=self.pd1, created_by=self.u2
        )
        if cache:
            cache.clear()

    def tearDown(self):
        StreamFilterAction.objects.all().delete()
        StreamFilterTrigger.objects.all().delete()
        StateTransition.objects.all().delete()
        State.objects.all().defer()
        StreamFilter.objects.all().delete()
        StreamData.objects.all().delete()
        Streamer.objects.all().delete()
        StreamerReport.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def _full_path(self, filename):
        module_path = os.path.dirname(__file__)
        return os.path.join(module_path, '..', '..', 'streamer', 'data', 'reports', filename)

    @skipIf(USE_WORKER, "Skip if using worker")
    @mock.patch('apps.streamer.report.worker.process_report.download_streamer_report_from_s3')
    def testReportParsing(self, mock_download_s3):

        f = StreamFilter.objects.create_filter_from_project_and_variable(
            name='Filter 1', proj=self.s1.project, var=self.s1.variable,
            created_by=self.u2
        )
        state1 = State.objects.create(label="state1", filter=f, created_by=self.u2)
        state2 = State.objects.create(label="state2", filter=f, created_by=self.u2)
        state3 = State.objects.create(label="state3", filter=f, created_by=self.u2)
        a1 = StreamFilterAction.objects.create(
            type='drv', created_by=self.u2, on='entry', state=state1,
            extra_payload={'output_stream':self.out_stream1.slug}
        )
        a2 = StreamFilterAction.objects.create(
            type='drv', created_by=self.u2, on='entry', state=state2,
            extra_payload={'output_stream':self.out_stream2.slug}
        )
        a3 = StreamFilterAction.objects.create(
            type='drv', created_by=self.u2, on='entry', state=state3,
            extra_payload={'output_stream':self.out_stream3.slug}
        )
        transition1 = StateTransition.objects.create(
            dst=state3, filter=f, created_by=self.u2
        )
        StreamFilterTrigger.objects.create(
            operator='ge', created_by=self.u2, filter=f, threshold=80, transition=transition1
        )
        transition2 = StateTransition.objects.create(
            dst=state2, filter=f, created_by=self.u2
        )
        StreamFilterTrigger.objects.create(
            operator='lt', created_by=self.u2, filter=f, threshold=80, transition=transition2
        )
        StreamFilterTrigger.objects.create(
            operator='gt', created_by=self.u2, filter=f, threshold=20, transition=transition2
        )
        transition3 = StateTransition.objects.create(
            dst=state1, filter=f, created_by=self.u2
        )
        StreamFilterTrigger.objects.create(
            operator='le', created_by=self.u2, filter=f, threshold=20, transition=transition3
        )

        url = reverse('streamerreport-list')
        url += '?timestamp={0}'.format('2017-01-10T10:00:00Z')

        test_filename = self._full_path('valid_100_readings.bin')
        self.s1.input_unit = None
        self.s1.save()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)
        with open(test_filename, 'rb') as fp:
            data = {
                'file': fp,
            }
            mock_download_s3.return_value = fp
            response = self.client.post(url, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            deserialized = json.loads(response.content.decode())
            self.assertEqual(deserialized['count'], 100)
            self.assertEqual(StreamerReport.objects.count(), 1)
            self.assertEqual(StreamData.objects.count(), 104)

            qs = StreamData.objects.filter(stream_slug=self.out_stream1).order_by('streamer_local_id')
            self.assertEqual(qs.count(), 1)
            self.assertEqual(qs.first().incremental_id, 1)
            qs = StreamData.objects.filter(stream_slug=self.out_stream2).order_by('streamer_local_id')
            self.assertEqual(qs.count(), 1)
            self.assertEqual(qs.first().incremental_id, 22)
            qs = StreamData.objects.filter(stream_slug=self.out_stream3).order_by('streamer_local_id')
            self.assertEqual(qs.count(), 1)
            self.assertEqual(qs.first().incremental_id, 81)

        self.client.logout()
