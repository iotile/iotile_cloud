import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import dateparse, timezone

from rest_framework import status
from rest_framework.test import APIClient

from apps.streamevent.models import StreamEventData
from apps.streamfilter.models import State, StateTransition, StreamFilter, StreamFilterAction, StreamFilterTrigger
from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.test_util import TestMixin
from apps.utils.utest.devices import TripDeviceMock

from ..generator.trip_update.generator import TripUpdateReportGenerator
from ..models import *
from ..worker.report_generator import *

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

    def testGeneratorPath(self):
        rpt = UserReport.objects.create(label='RPT1', generator='trip_update', org=self.o2, created_by=self.u2)
        module_path, class_name = ReportGenerator._generator_package_path(rpt.generator)
        self.assertEqual(module_path, 'apps.report.generator.trip_update.generator')
        self.assertEqual(class_name, 'TripUpdateReportGenerator')
        generator_class = ReportGenerator.get_generator_class(rpt)
        rg = generator_class([], rpt, timezone.now(), timezone.now())
        self.assertTrue(isinstance(rg, TripUpdateReportGenerator))

    def testBasicProcessReportAction(self):
        config = {}
        rpt1 = UserReport.objects.create(
            label='RPT1',
            interval='d',
            generator='trip_update',
            config=config,
            created_by=self.u2,
            org=self.o2
        )

        # First try with no event
        action = ReportGeneratorAction()
        action.process_user_report(rpt1, start=None, end=None, orginal_sources=[self.pd1.slug,])
        self.assertEqual(len(action._msgs), 0)

        # Now ad trip update event and try again
        stream_slug = self.pd1.get_stream_slug_for(SYSTEM_VID['TRIP_UPDATE'])
        event = StreamEventData.objects.create(
            stream_slug=str(stream_slug),
            timestamp=timezone.now(),
            extra_data={
                "Below 17C": 81000,
                "Max Peak (G)": 40.621,
                "Min Temp (C)": 22.56,
                "Max Humidity (% RH)": 39.634765625,
                "DeltaV at Max Peak (in/s)": 52.67529065551758
            }
        )
        self.assertEqual(StreamEventData.objects.filter(stream_slug=str(stream_slug)).count(), 1)

        action = ReportGeneratorAction()
        action.process_user_report(rpt1, start=None, end=None, orginal_sources=[self.pd1.slug,])
        self.assertEqual(len(action._msgs), 0)
        event = StreamEventData.objects.get(pk=event.id)
        self.assertEqual(event.extra_data['Below 17C'], '22:30:0')
        self.assertEqual(event.extra_data['Max Peak (G)'], 40.62)
        self.assertEqual(event.extra_data['Min Temp (C)'], 22.56)
        self.assertEqual(event.extra_data['Max Humidity (% RH)'], 39.63)
        self.assertEqual(event.extra_data['DeltaV at Max Peak (in/s)'], 52.68)

    def testEventApiWithFilter(self):
        url = reverse('streameventdata-list')
        t1 = timezone.now()

        self.assertEqual(StreamEventData.objects.count(), 10)

        stream = StreamId.objects.filter(device=self.pd1, variable__slug='v--0000-0002--5a08').first()
        payload = {
            'stream': stream.slug,
            'timestamp': t1,
            'streamer_local_id': 2,
            'extra_data': {
                "Below 17C": 81000,
                "Max Peak (G)": 40.621,
                "Min Temp (C)": 22.56,
                "Max Humidity (% RH)": 39.634765625,
                "DeltaV at Max Peak (in/s)": 52.67529065551758
            }
        }
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream.slug).count(), 0)

        f = StreamFilter.objects.create_filter_from_streamid(name='test',
                                                             input_stream=stream,
                                                             created_by=self.u1)
        state = State.objects.create(label='state1', filter=f, created_by=self.u2)
        a = StreamFilterAction.objects.create(
            type='smry', created_by=self.u1,  on='entry', state=state,  extra_payload={
                'generator': 'trip_update', 'notification_recipients': ['email:david@example.com']
            },
        )
        transition = StateTransition.objects.create(src=state, dst=state, filter=f, created_by=self.u2)
        t = StreamFilterTrigger.objects.create(operator="bu", threshold=None, created_by=self.u1, filter=f, transition=transition)

        api_client = APIClient()

        ok = api_client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = api_client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamEventData.objects.count(), 11)
        self.assertEqual(StreamEventData.objects.filter(stream_slug=stream.slug).count(), 1)

        # TODO: Not really testing here. What can we check for?
        # Hard to test because the code assumes workers are used, and if not used
        # the filters are processed before the event has been committed so nothing is done

        api_client.logout()

