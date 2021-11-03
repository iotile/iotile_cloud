from unittest import mock

from django.core.exceptions import PermissionDenied

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from iotile_cloud.utils.gid import *

from apps.utils.test_util import TestMixin
from apps.streamevent.models import StreamEventData

from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.utest.devices import TripDeviceMock
from apps.utils.rest.exceptions import ApiIllegalSlugException
from apps.org.models import OrgMembership

from ..models import *
from ..worker.report_generator import *
from ..serializers import ScheduleAnalyticsReportSerializer

user_model = get_user_model()


class ReportGeneratorAPITestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()

        self.device_mock = TripDeviceMock()

        self.o1 = Org.objects.create_org(name='Vendor', created_by=self.u1, is_vendor=True)

        self.o2 = Org.objects.get(slug='user-org')
        self.o2.register_user(self.u2, role='a1')

        self.o3 = Org.objects.create_org(name='User Org3', created_by=self.u3)
        self.o3.register_user(self.u3)
        self.p1 = Project.objects.get(name='Project 1')
        self.pd1 = self.p1.devices.first()

    def tearDown(self):
        self.device_mock.tearDown()

        self.userTestTearDown()

    def testGeneratedReportGet(self):
        rpt = UserReport.objects.create(label='RPT1', org=self.o2, created_by=self.u2)

        g1 = GeneratedUserReport.objects.create(
            report=rpt,
            org=self.o2,
            label='My report 1',
            source_ref='d--0000-0000-0000-0001',
            created_by=self.u2
        )
        g2 = GeneratedUserReport.objects.create(
            report=rpt,
            org=self.o2,
            label='My report 2',
            source_ref='d--0000-0000-0000-0002',
            created_by=self.u2
        )
        g2 = GeneratedUserReport.objects.create(
            report=rpt,
            org=self.o1,
            label='My report 3',
            source_ref='d--0000-0000-0000-0003',
            created_by=self.u1
        )
        url_list = reverse('generateduserreport-list')
        url_detail = reverse('generateduserreport-detail', kwargs={'pk': str(g1.id)})

        response = self.client.get(url_list, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url_list, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.get(url_list+'?staff=1', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url_list+'?staff=1&org={}'.format(self.o2.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        response = self.client.get(url_list+'?staff=1&org={}'.format(self.o1.slug), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.get(url_detail, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['id'], str(g1.id))

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.o2.has_access(self.u2))

        response = self.client.get(url_list, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)

        response = self.client.get(url_detail, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['id'], str(g1.id))

        g3 = GeneratedUserReport.objects.create(
            report=rpt,
            org=self.o2,
            label='My report 3',
            source_ref='d--0000-0000-0000-0002',
            created_by=self.u2,
            status='GE'
        )

        response = self.client.get(url_list, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 3)

        response = self.client.get(url_list+'?source_ref=d--0000-0000-0000-0002', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 2)
        self.assertEqual(deserialized['results'][0]['source_ref'], 'd--0000-0000-0000-0002')
        self.assertEqual(deserialized['results'][1]['source_ref'], 'd--0000-0000-0000-0002')

        response = self.client.get(url_list+'?status=GE', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['status'], 'GE')

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url_list, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url_list+'?staff=1', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(url_detail, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        g4 = GeneratedUserReport.objects.create(
            report=rpt,
            org=self.o3,
            label='My report 4',
            source_ref='d--0000-0000-0000-0011',
            created_by=self.u3
        )

        response = self.client.get(url_list, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url_list+'?staff=1', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 5)

        self.client.logout()

    def testGeneratedReportPost(self):
        rpt = UserReport.objects.create(label='RPT1', org=self.o2, created_by=self.u2)
        self.assertEqual(rpt.generated_reports.count(), 0)

        payload = {
            'report': rpt.id,
            'org': self.o2.slug,
            'label': 'My report 1',
            'source_ref': 'd--0000-0000-0000-0001',
        }
        url = reverse('generateduserreport-list')

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(rpt.generated_reports.count(), 1)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.o2.has_access(self.u2))

        payload['label'] = 'My report 2'
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(rpt.generated_reports.count(), 2)

        payload['label'] = 'My report 3'
        del(payload['report'])
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(rpt.generated_reports.count(), 2)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testGeneratedReportGenrationProcess(self):
        rpt = UserReport.objects.create(label='RPT1', org=self.o2, created_by=self.u2)

        payload = {
            'report': rpt.id,
            'org': self.o2.slug,
            'label': 'My report 1',
            'status': 'GS',
            'source_ref': 'd--0000-0000-0000-0001',
        }
        url = reverse('generateduserreport-list')

        self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(self.o2.has_access(self.u2))

        # 1.- The report is first created
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(GeneratedUserReport.objects.count(), 1)
        generated = GeneratedUserReport.objects.first()
        self.assertEqual(generated.status, 'GS')
        self.assertEqual(generated.label, 'My report 1')
        self.assertEqual(generated.source_ref, 'd--0000-0000-0000-0001')
        self.assertIsNone(generated.index_file)

        # 2.- Set report to InProgress
        payload = {
            'status': 'G0'
        }
        url = reverse('generateduserreport-detail', kwargs={'pk': str(generated.id)})
        response = self.client.patch(url, payload, format='json')
        deserialized = json.loads(response.content.decode())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(deserialized['status'], 'G0')

        # 3.- Set report as complete
        payload = {
            'status': 'G1',
            'key': 'index.html'
        }
        url = reverse('generateduserreport-detail', kwargs={'pk': str(generated.id)})
        response = self.client.patch(url, payload, format='json')
        deserialized = json.loads(response.content.decode())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(deserialized['status'], 'G1')
        self.assertEqual(deserialized['index_file']['id'], deserialized['id'])
        self.assertEqual(deserialized['index_file']['title'], deserialized['label'])

        self.client.logout()

    def testS3FileAttachUrl(self):
        """
        Ensure we can create a new s3file with the script
        """
        rpt = UserReport.objects.create(label='RPT1', org=self.o2, created_by=self.u2)
        generated = GeneratedUserReport.objects.create(
            report=rpt,
            org=self.o2,
            source_ref='d--0001',
            label='My Report',
            created_by=self.u2
        )

        url = reverse('generateduserreport-uploadurl', kwargs={'pk': str(generated.id)})

        payload = {
            'name': 'index.html',
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(GeneratedUserReport.objects.count(), 1)
        self.assertEqual(S3File.objects.count(), 0)
        deserialized = json.loads(response.content.decode())
        self.assertTrue('url' in deserialized)
        self.assertTrue('uuid' in deserialized)
        self.assertTrue('fields' in deserialized)
        self.assertTrue('acl' in deserialized['fields'])
        self.assertEqual(deserialized['fields']['acl'], 'private')
        self.assertEqual(deserialized['fields']['Content-Type'], 'text/html')
        self.assertEqual(deserialized['fields']['x-amz-meta-filename'], 'index.html')
        self.assertEqual(deserialized['fields']['x-amz-meta-uuid'], str(generated.id))
        self.assertEqual(deserialized['fields']['x-amz-meta-type'], 'report')

        """
        import os
        import requests
        test_filename = __file__
        self.assertTrue(os.path.isfile(test_filename))
        with open(test_filename, 'r') as fp:
            files = {"file": fp}
            response = requests.post(deserialized["url"], data=deserialized["fields"], files=files)
            print(response)
        """

        # Now test we can upload associated files as public
        payload = {
            'name': 'data/waveform1.json',
            'acl': 'public-read',
            'content_type': 'application/json'
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(GeneratedUserReport.objects.count(), 1)
        self.assertEqual(S3File.objects.count(), 0)
        deserialized = json.loads(response.content.decode())
        self.assertTrue('url' in deserialized)
        self.assertTrue('uuid' in deserialized)
        self.assertTrue('fields' in deserialized)
        self.assertTrue('acl' in deserialized['fields'])
        self.assertEqual(deserialized['fields']['acl'], 'public-read')
        self.assertEqual(deserialized['fields']['Content-Type'], 'application/json')
        self.assertEqual(deserialized['fields']['x-amz-meta-filename'], 'waveform1.json')
        self.assertEqual(deserialized['fields']['x-amz-meta-uuid'], str(generated.id))
        self.assertEqual(deserialized['fields']['x-amz-meta-type'], 'report')

        payload = {
            'name': 'data/foo.json',
            'content_type': 'bad type'
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.logout()

    def testS3FileAttachSuccess(self):
        """
        Ensure we can create a new s3file with the report
        """
        rpt = UserReport.objects.create(label='RPT1', org=self.o2, created_by=self.u2)
        generated = GeneratedUserReport.objects.create(
            report=rpt,
            org=self.o2,
            source_ref='d--0001',
            label='My Report',
            created_by=self.u2
        )

        url = reverse('generateduserreport-uploadsuccess', kwargs={'pk': str(generated.id)})

        payload = {
            'name': 'index.html'
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(GeneratedUserReport.objects.count(), 1)
        self.assertEqual(S3File.objects.count(), 1)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['id'], str(generated.id))
        self.assertEqual(deserialized['title'], generated.label)
        self.assertEqual(deserialized['file_type'], 'html')
        self.assertEqual(deserialized['created_by'], self.u2.id)
        self.assertIsNotNone(deserialized['url'])

        g1 = GeneratedUserReport.objects.get(pk=generated.id)
        self.assertIsNotNone(g1.index_file)
        self.assertEqual(g1.index_file.id, g1.id)
        # self.assertEqual(g1.index_file.url, deserialized['url'])
        self.assertEqual(g1.index_file.key, 'dev/shared/{}/{}/index.html'.format(self.o2.slug, str(g1.id)))

        # Test that we can upload another file and update it
        payload = {
            'name': 'index2.html'
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(GeneratedUserReport.objects.count(), 1)
        self.assertEqual(S3File.objects.count(), 1)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['id'], str(generated.id))

        g1 = GeneratedUserReport.objects.get(pk=generated.id)
        self.assertIsNotNone(g1.index_file)
        self.assertEqual(g1.index_file.id, g1.id)
        self.assertEqual(g1.index_file.key, 'dev/shared/{}/{}/index2.html'.format(self.o2.slug, str(g1.id)))

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testAnalyticsSerializer(self):
        payload = {
            'slug': 'd--1234',
            'template': 'default'
        }
        serializer = ScheduleAnalyticsReportSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

        payload['template'] = 'bad-template'
        serializer = ScheduleAnalyticsReportSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

        payload['template'] = 'shipment_overview'
        serializer = ScheduleAnalyticsReportSerializer(data=payload)
        self.assertTrue(serializer.is_valid())

        with self.assertRaises(PermissionDenied):
            serializer.save(user=self.u2)

        payload['slug'] = 'foo'
        serializer = ScheduleAnalyticsReportSerializer(data=payload)
        self.assertTrue(serializer.is_valid())
        with self.assertRaises(ApiIllegalSlugException):
            serializer.save(user=self.u2)

        payload['slug'] = self.pd1.slug
        serializer = ScheduleAnalyticsReportSerializer(data=payload)
        self.assertTrue(serializer.is_valid())
        result = serializer.save(user=self.u2)
        self.assertIsNotNone(result['report'])
        self.assertEqual(result['group_slug'], self.pd1.slug)
        self.assertEqual(result['template'], 'shipment_overview')
        self.assertEqual(result['user'], self.u2.email)
        self.assertEqual(result['token'], self.u2.jwt_token)
        self.assertIsNone(result['args'])

        payload['args'] = {
            'foo': 'bar',
            'foobar': True
        }
        serializer = ScheduleAnalyticsReportSerializer(data=payload)
        self.assertTrue(serializer.is_valid())
        result = serializer.save(user=self.u2)
        self.assertIsNotNone(result['args'])
        self.assertEqual(result['args']['foo'], 'bar')
        self.assertEqual(result['args']['foobar'], True)

    @mock.patch('apps.utils.aws.sqs.get_queue_by_name')
    @mock.patch('apps.report.api_views.SqsPublisher.publish')
    def testScheduleReport(self, mock_sqs, mock_get_q):
        mock_get_q.return_value = ''
        url = reverse('generateduserreport-schedule')
        payload = {
            'slug': 'd--1234', # Not in Org
            'template': 'default' # Not allowed
        }
        self.assertEqual(GeneratedUserReport.objects.count(), 0)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        payload['template'] = 'shipment_overview'
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        payload['slug'] = self.pd1.slug
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(response.content.decode())
        mock_sqs.assert_called_with(payload=deserialized)
        self.assertEqual(GeneratedUserReport.objects.count(), 1)
        report = GeneratedUserReport.objects.last()
        self.assertEqual(report.label, 'shipment_overview: {}'.format(self.pd1.slug))
        self.assertEqual(report.org, self.pd1.org)
        self.assertEqual(report.source_ref, self.pd1.slug)
        self.assertEqual(report.status, 'GS')
        self.assertFalse(report.public)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload['args'] = {
            'foo': 'bar'
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(response.content.decode())
        mock_sqs.assert_called_with(payload=deserialized)
        self.assertEqual(GeneratedUserReport.objects.count(), 2)

        payload['label'] = 'My Label'
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(response.content.decode())
        mock_sqs.assert_called_with(payload=deserialized)
        self.assertEqual(GeneratedUserReport.objects.count(), 3)
        report = GeneratedUserReport.objects.last()
        self.assertEqual(report.label, 'My Label')

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testAvailabilityReport(self):
        url = reverse('generateduserreport-availability')
        payload = {
            'slug': 'd--1234'
        }
        self.assertEqual(GeneratedUserReport.objects.count(), 0)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['slug'], 'N/A')
        self.assertEqual(deserialized['code'], 'NOT_SUPPORTED')

        self.client.logout()



