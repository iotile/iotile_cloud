import json
import os
import dateutil.parser
from unittest import skipIf, mock

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
from apps.utils.iotile.streamer import STREAMER_SELECTOR
from apps.utils.dynamic_loading import str_to_class

from .models import *
from .serializers import *
from .report.parser import ReportParser
from .worker.common.types import ENGINE_TYPES

user_model = get_user_model()
USE_WORKER = getattr(settings, 'USE_WORKER')


class StreamerTestCase(TestMixin, TestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=1,
        )
        self.v2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p2, created_by=self.u3, lid=2,
        )
        sg = SensorGraph.objects.create_graph(name='SG1', report_processing_engine_ver=0, created_by=self.u2, org=self.o1)
        self.pd1 = Device.objects.create_device(project=self.p1, sg=sg, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p2, sg=sg, label='d2', template=self.dt1, created_by=self.u3)
        StreamId.objects.create_after_new_device(self.pd1)
        StreamId.objects.create_after_new_device(self.pd2)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()
        self.s2 = StreamId.objects.filter(variable=self.v2).first()
        self.assertEqual(Device.objects.count(), 2)


    def tearDown(self):
        Streamer.objects.all().delete()
        StreamerReport.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testObjectSlug(self):
        streamer = Streamer.objects.create(device=self.pd1, index=1, created_by=self.u1 )
        dev_id = self.pd1.formatted_gid
        self.assertEqual(streamer.slug, 't--{}--0001'.format(dev_id))
        self.assertEqual(str(streamer), 't--{}--0001'.format(dev_id))

        streamer.index = 2
        streamer.save()
        self.assertEqual(streamer.slug, 't--{}--0002'.format(dev_id))

    def testStreamerReport(self):
        streamer = Streamer.objects.create(device=self.pd1, index=1, created_by=self.u1 )
        report = StreamerReport.objects.create(streamer=streamer, actual_first_id=11, actual_last_id=20, created_by=self.u1 )
        self.assertEqual(report.num_entries, 10)

    def testDateTimeUtilitiesForceToUtc(self):
        # Test that we can force a dt into UTC
        dt = force_to_utc('2017-01-10T10:00:00')
        self.assertEqual(str_utc(dt), '2017-01-10T10:00:00Z')
        dt = force_to_utc('2017-01-10T10:00:00Z')
        self.assertEqual(str_utc(dt), '2017-01-10T10:00:00Z')
        dt = force_to_utc('2017-04-27T21:30:30.453786+00:00')
        self.assertEqual(str_utc(dt), '2017-04-27T21:30:30Z')
        dt = force_to_utc('2017-04-27T21:30:30.453786')
        self.assertEqual(str_utc(dt), '2017-04-27T21:30:30Z')
        dt = force_to_utc('2017-04-27T21:30:30+08:00')
        self.assertEqual(str_utc(dt), '2017-04-27T13:30:30Z')

    def testActionModules(self):
        for ver in ENGINE_TYPES.keys():
            for ext in ENGINE_TYPES[ver]:
                item = ENGINE_TYPES[ver][ext]
                action_class = str_to_class(item['module_name'], item['class_name'])
                self.assertEqual(item['class_name'], action_class.__name__)


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

    def tearDown(self):
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
        return os.path.join(module_path, 'data', 'reports', filename)

    def testApiSerializer(self):
        payload = {}
        serializer = StreamerSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

        payload = {
            'device': self.pd1.slug,
            'last_id': 100
        }
        serializer = StreamerSerializer(data=payload)
        self.assertTrue(serializer.is_valid())

    def testInvalidKeys(self):
        streamer = Streamer.objects.create(device=self.pd1, index=1, created_by=self.u1 )
        streamer_url = reverse('streamer-detail', kwargs={'slug': 'bad-word'})
        StreamerReport.objects.create(streamer=streamer, created_by=self.u1)
        report_url = reverse('streamerreport-detail', kwargs={'pk': 'bad-word'})

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(streamer_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.get(report_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized[0], 'Streamer Report ID must be a UUID')

        report_url = reverse('streamerreport-detail', kwargs={'pk': str(uuid.uuid4())})
        resp = self.client.get(report_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.logout()

    def testGet(self):
        url = reverse('streamer-list')
        d0 = Device.objects.create_device(project=self.p1, sg=self.sg,
                                          label='d1', template=self.dt1, created_by=self.u2)
        d1 = Device.objects.create_device(project=self.p1, sg=self.sg,
                                          label='d2', template=self.dt1, created_by=self.u2)
        d2 = Device.objects.create_device(project=self.p2, sg=self.sg,
                                          label='d3', template=self.dt1, created_by=self.u3)
        streamer1_0 = Streamer.objects.create(device=d0, index=0,
                                              selector=STREAMER_SELECTOR['USER_NO_REBOOTS'], created_by=self.u1 )
        Streamer.objects.create(device=d0, index=1,
                                selector=STREAMER_SELECTOR['SYSTEM'], created_by=self.u1 )
        Streamer.objects.create(device=d1, index=0,
                                selector=STREAMER_SELECTOR['USER'], created_by=self.u1 )
        Streamer.objects.create(device=d1, index=1,
                                selector=STREAMER_SELECTOR['SYSTEM'], created_by=self.u1 )
        url1 = reverse('streamer-detail', kwargs={'slug': streamer1_0.slug})

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 4)

        response = self.client.get(url1+'?staff=1', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['slug'], streamer1_0.slug)
        self.assertEqual(deserialized['index'], 0)
        self.assertEqual(deserialized['last_id'], 0)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 4)
        response = self.client.get(url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(url+'?device={}'.format(d0.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)
        for item in deserialized['results']:
            self.assertEqual(item['device'], d0.slug)

        response = self.client.get(url+'?device=d--{}'.format(int16gid(d0.id)), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)
        for item in deserialized['results']:
            self.assertEqual(item['device'], d0.slug)

        response = self.client.get(url+'?selector={}'.format(STREAMER_SELECTOR['USER']), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        for item in deserialized['results']:
            self.assertEqual(item['selector'], STREAMER_SELECTOR['USER'])

        response = self.client.get(url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['slug'], streamer1_0.slug)
        self.assertEqual(deserialized['index'], 0)
        self.assertEqual(deserialized['last_id'], 0)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)
        response = self.client.get(url1, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        s2 = Streamer.objects.create(device=d2, index=1,
                                     selector=STREAMER_SELECTOR['USER'], created_by=self.u1 )

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        url2 = reverse('streamer-detail', kwargs={'slug': s2.slug})
        response = self.client.get(url2, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testPost(self):
        url = reverse('streamer-list')
        payload = {
            'device': self.pd1.slug,
            'index': 1,
            'last_id': 100
        }

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['slug'], 't--{0}--0001'.format(self.pd1.formatted_gid))

        self.client.logout()

    def testNoAccessForUsers(self):
        url = reverse('streamer-list')
        payload = {
            'device': self.pd1.slug,
            'index': 1,
            'last_id': 100
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testStreamerReportAPIGET(self):
        d0 = Device.objects.create_device(
            project=self.p1, sg=self.sg, label='d1', template=self.dt1, created_by=self.u2
        )
        d1 = Device.objects.create_device(
            project=self.p2, sg=self.sg, label='d2', template=self.dt1, created_by=self.u3
        )
        streamer1 = Streamer.objects.create(
            device=d0, index=0, selector=0xff, created_by=self.u2
        )
        streamer2 = Streamer.objects.create(
            device=d0, index=1, selector=0xfe, created_by=self.u2
        )
        streamer3 = Streamer.objects.create(
            device=d1, index=0, selector=0xff, created_by=self.u3
        )

        StreamerReport.objects.create(
            streamer=streamer1, created_by=self.u2,
            sent_timestamp=parse_datetime("2017-01-10T10:00:00Z")
        )
        StreamerReport.objects.create(
            streamer=streamer2, created_by=self.u2,
            sent_timestamp=parse_datetime("2017-01-10T11:00:00Z")
        )
        StreamerReport.objects.create(
            streamer=streamer2, created_by=self.u2,
            sent_timestamp=parse_datetime("2017-01-10T12:00:00Z")
        )
        StreamerReport.objects.create(
            streamer=streamer3, created_by=self.u2,
            sent_timestamp=parse_datetime("2017-01-10T10:00:00Z")
        )

        url = reverse('streamerreport-list')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 4)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url+'?streamer__slug={}'.format(streamer2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)
        self.assertEqual(deserialized['results'][0]['sent_timestamp'], "2017-01-10T11:00:00Z")
        self.assertEqual(deserialized['results'][1]['sent_timestamp'], "2017-01-10T12:00:00Z")

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['streamer'], streamer3.slug)

        self.client.logout()

    @mock.patch('apps.streamer.worker.common.base_action.ProcessReportBaseAction.schedule')
    @mock.patch('apps.streamer.report.worker.process_report.download_streamer_report_from_s3')
    def testReportUpload(self, mock_download_s3, mock_process_report_schedule):

        url = reverse('streamerreport-list')

        test_filename = self._full_path('valid_100_readings.bin')

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            response = self.client.post(url, {'file': fp}, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            response = self.client.post(url, {'file': fp}, format='multipart')
            # 400 if no ?timestamp=
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        url += '?timestamp={0}'.format('2016-09-28T10:00:00Z')

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            response = self.client.post(url, {'file': fp}, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.first().created_by, self.u1)

        self.client.logout()

    @mock.patch('apps.streamer.worker.common.base_action.ProcessReportBaseAction.schedule')
    @mock.patch('apps.streamer.report.worker.process_report.download_streamer_report_from_s3')
    def testUploadBadTimestamp(self, mock_download_s3, mock_process_report_schedule):

        url = reverse('streamerreport-list')

        test_filename = self._full_path('valid_16_readings.bin')
        self.s1.input_unit = None
        self.s1.save()

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            ok = self.client.login(email='user1@foo.com', password='pass')
            self.assertTrue(ok)

            data = {
                'file': fp,
            }
            response = self.client.post(url, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

            url1 = url + '?timestamp={0}'.format('2017-01-10T10:00:00+02:00')
            fp.seek(0)
            response = self.client.post(url1, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

            url1 = url + '?timestamp={0}'.format('2017-01-10T10:00:00')
            fp.seek(0)
            response = self.client.post(url1, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @skipIf(USE_WORKER, "Skip if using worker")
    @mock.patch('apps.streamer.report.worker.process_report.download_streamer_report_from_s3')
    def testReportParsing(self, mock_download_s3):

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
            self.assertEqual(StreamData.objects.count(), 101)

            report = StreamerReport.objects.first()
            self.assertTrue(report.successful)
            self.assertEqual(report.original_first_id, 1)  # Normal reports will not have a 0, but this report does
            self.assertEqual(report.original_last_id, 100)
            self.assertEqual(report.actual_first_id, 1)  # 0 is ignored as that should not be legal
            self.assertEqual(report.actual_last_id, 100)
            self.assertEqual(report.num_entries, 100)
            self.assertEqual(str(report.sent_timestamp.isoformat()), '2017-01-10T10:00:00+00:00')
            streamer = report.streamer
            self.assertEqual(streamer.last_id, 100)

            first = StreamData.objects.order_by('stream_slug', 'streamer_local_id', 'timestamp').first()
            self.assertEqual(first.int_value, 0)
            self.assertEqual(first.value, 0.0) # old scheme
            self.assertEqual(first.streamer_local_id, 1)
            self.assertEqual(first.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
            self.assertEqual(first.project_slug, 'p--0000-0002')
            self.assertEqual(first.device_slug, 'd--0000-0000-0000-000a')
            self.assertEqual(first.variable_slug, 'v--0000-0002--5001')
            self.assertEqual(first.device_timestamp, 0)
            self.assertEqual(str(first.timestamp.isoformat()), '2017-01-10T10:00:00+00:00')

            last = StreamData.objects.filter(variable_slug__endswith='5001').last()
            self.assertEqual(last.int_value, 99)
            self.assertEqual(last.value, 99.0) # Old scheme
            self.assertEqual(last.streamer_local_id, 100)
            self.assertEqual(last.stream_slug, 's--0000-0002--0000-0000-0000-000a--5001')
            self.assertEqual(last.project_slug, 'p--0000-0002')
            self.assertEqual(last.device_slug, 'd--0000-0000-0000-000a')
            self.assertEqual(last.variable_slug, 'v--0000-0002--5001')
            self.assertEqual(last.device_timestamp, 99)
            self.assertEqual(str(last.timestamp.isoformat()), '2017-01-10T10:01:39+00:00')

        StreamerReport.objects.all().delete()
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
            self.assertEqual(StreamData.objects.count(), 101)

            report = StreamerReport.objects.last()
            self.assertEqual(report.original_first_id, 1)
            self.assertEqual(report.original_last_id, 100)
            self.assertEqual(report.actual_first_id, 0)
            self.assertEqual(report.actual_last_id, 0)
            self.assertEqual(report.num_entries, 0)

        self.client.logout()

    @mock.patch('apps.streamer.worker.common.base_action.ProcessReportBaseAction.schedule')
    @mock.patch('apps.streamer.report.worker.process_report.download_streamer_report_from_s3')
    def testUploadNoExtensionReport(self, mock_download_s3, mock_process_report_schedule):

        url = reverse('streamerreport-list')

        test_filename = self._full_path('valid_16_readings_no_ext')
        self.s1.input_unit = None
        self.s1.save()

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            ok = self.client.login(email='user1@foo.com', password='pass')
            self.assertTrue(ok)

            data = {
                'file': fp,
            }

            url1 = url + '?timestamp={0}'.format('2017-01-10T10:00:00')
            fp.seek(0)
            response = self.client.post(url1, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            deserialized = json.loads(response.content.decode())
            self.assertEqual(deserialized['count'], 16)

        self.assertEqual(StreamerReport.objects.count(), 1)

    @mock.patch('apps.streamer.report.worker.process_report.download_streamer_report_from_s3')
    def testIllegalReportUpload(self, mock_download_s3):

        url = reverse('streamerreport-list')
        url += '?timestamp={0}'.format('2017-01-10T10:00:00Z')

        test_filename = self._full_path('not_a_report.jpg')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            data = {
                'file': fp,
            }
            response = self.client.post(url, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            deserialized = json.loads(response.content.decode())
            self.assertEqual(len(deserialized), 1)
            self.assertEqual(deserialized[0],
                             "Streamer Report file extension not supported. Expected: .bin, .json or .mp")

        self.client.logout()

    @mock.patch('apps.streamer.report.worker.process_report.download_streamer_report_from_s3')
    def testInvalidFooter(self, mock_download_s3):
        url = reverse('streamerreport-list')
        url += '?timestamp={0}'.format('2017-01-10T10:00:00Z')

        test_filename = self._full_path('invalid_footer_16_readings.bin')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            data = {
                'file': fp,
            }
            response = self.client.post(url, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            deserialized = json.loads(response.content.decode())
            self.assertEqual(len(deserialized), 1)
            self.assertEqual(deserialized[0], 'Invalid Hash: d--0000-0000-0000-000a (idx=0, user=@User1)')

        self.client.logout()

    @mock.patch('apps.streamer.worker.common.base_action.ProcessReportBaseAction.schedule')
    @mock.patch('apps.streamer.report.worker.process_report.download_streamer_report_from_s3')
    def testStreamerReportAPI(self, mock_download_s3, mock_process_report_schedule):

        streamer = Streamer.objects.create(device=self.pd1, index=0, created_by=self.u1 )
        url = reverse('streamerreport-list')
        url += '?timestamp={0}'.format('2017-01-10T10:00:00Z')

        reports_url = reverse('streamer-report', kwargs={'slug': streamer.slug})

        test_filename = self._full_path('valid_100_readings.bin')

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            ok = self.client.login(email='user1@foo.com', password='pass')
            self.assertTrue(ok)

            data = {
                'file': fp,
            }
            response = self.client.post(url, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            data = {
                'file': fp,
            }
            response = self.client.post(url, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(reports_url+'?staff=1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(len(deserialized), 2)

        self.client.logout()

    @mock.patch('apps.streamer.worker.common.base_action.ProcessReportBaseAction.schedule')
    @mock.patch('apps.streamer.report.worker.process_report.download_streamer_report_from_s3')
    def testLargeReportUpload(self, mock_download_s3, mock_process_report_schedule):

        url = reverse('streamerreport-list')
        url += '?timestamp={0}'.format('2017-01-10T10:00:00Z')

        test_filename = self._full_path('valid_10000_readings.bin')

        with open(test_filename, 'rb') as fp:
            mock_download_s3.return_value = fp
            ok = self.client.login(email='user1@foo.com', password='pass')
            self.assertTrue(ok)

            data = {
                'file': fp,
            }
            response = self.client.post(url, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            deserialized = json.loads(response.content.decode())
            self.assertEqual(deserialized['count'], 10000)
            self.assertEqual(StreamerReport.objects.count(), 1)

    def testDeviceApi(self):

        url = reverse('device-streamers', kwargs={'slug': str(self.pd1.slug)})

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(len(deserialized), 0)

        streamer = Streamer.objects.create(device=self.pd1, index=0, created_by=self.u1 )

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(len(deserialized), 1)
        self.assertEqual(deserialized[0]['slug'], streamer.slug)
        self.assertEqual(deserialized[0]['index'], streamer.index)
        self.assertEqual(deserialized[0]['last_id'], streamer.last_id)

        self.client.logout()

    @skipIf(USE_WORKER, "Skip if using worker")
    @mock.patch('apps.streamer.report.worker.process_report.download_streamer_report_from_s3')
    def testNewSchemeInputUnits(self, mock_download_s3):

        url = reverse('streamerreport-list')
        url += '?timestamp={0}'.format('2017-02-10T10:00:00Z')

        test_filename = self._full_path('valid_16_readings.bin')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        with open(test_filename, 'rb') as fp:

            data = {
                'file': fp,
            }
            mock_download_s3.return_value = fp
            response = self.client.post(url, data, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        data1 = StreamData.objects.order_by('stream_slug', 'streamer_local_id', 'timestamp').first()
        self.assertEqual(data1.int_value, 0)
        # self.assertEqual(data1.value, 0.0)
        data16 = StreamData.objects.filter(variable_slug__endswith='5001').last()
        self.assertEqual(data16.int_value, 15)
        # self.assertEqual(data16.value, 3.0)
