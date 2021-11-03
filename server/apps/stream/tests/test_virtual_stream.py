import json
import datetime
import dateutil.parser
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone, dateparse

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.physicaldevice.models import Device
from apps.projecttemplate.models import ProjectTemplate
from apps.vartype.models import *
from apps.utils.test_util import TestMixin
from apps.utils.gid.convert import *
from apps.utils.timezone_utils import str_utc
from apps.streamdata.models import StreamData
from django.utils.dateparse import parse_datetime


from ..models import *

user_model = get_user_model()


class VirtualStreamAPITests(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testCreateVirtualStreams(self):
        """
        Test that we can create a Virtual Stream via the API
        """
        self.assertTrue(self.p1.org.has_access(self.u2))

        stream_url = reverse('streamid-list')
        variable_url = reverse('streamvariable-list')

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        # 1.- Create Variable
        payload = {
            'name': 'Go to Gym',
            'project': str(self.p1.id),
            'lid': 1
        }

        response = self.client.post(variable_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        variable_deserialized = json.loads(response.content.decode())

        # 2.- Create Stream
        payload = {
            'variable': variable_deserialized['slug'],
            'data_label': 'Go to the Gym'
        }

        response = self.client.post(stream_url, data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        stream_deserialized = json.loads(response.content.decode())

        self.assertEqual(variable_deserialized['slug'], stream_deserialized['variable'])
        self.assertEqual(stream_deserialized['org'], variable_deserialized['org'])
        self.assertEqual(stream_deserialized['project'], self.p1.slug)
        self.assertIsNone(stream_deserialized['device'])
        self.assertEqual(variable_deserialized['project'], str(self.p1.id))
        self.assertEqual(stream_deserialized['multiplication_factor'], 1)
        self.assertEqual(stream_deserialized['division_factor'], 1)
        self.assertEqual(stream_deserialized['offset'], 0.0)
        self.assertEqual(stream_deserialized['data_label'], 'Go to the Gym')

        # 3.- Get Virtual Streams
        # But by default streams do not return virtual streams
        response = self.client.get(stream_url+'?project={}'.format(self.p1.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        # "virtual=1"
        response = self.client.get(stream_url+'?project={}&virtual=1'.format(self.p1.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['slug'], stream_deserialized['slug'])

        # 4.- Add Data
        data_url = reverse('streamdata-list')
        payload = {
            'stream': stream_deserialized['slug'],
            'type': 'Num',
            'timestamp': timezone.now(),
            'int_value': 1,
        }
        response = self.client.post(data_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StreamData.objects.count(), 1)
        stream_data = StreamData.objects.last()
        self.assertEqual(stream_data.int_value, 1)
        self.assertEqual(stream_data.value, 1.0)

        # 5.- Get Data
        response = self.client.get(data_url+'?filter={}'.format(stream_deserialized['slug']), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['int_value'], 1)
        self.assertEqual(deserialized['results'][0]['value'], 1.0)

        stream_data_url = reverse('streamid-data', kwargs={'slug': stream_deserialized['slug']})
        response = self.client.get(stream_data_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['int_value'], 1)
        self.assertEqual(deserialized['results'][0]['value'], 1.0)

        self.client.logout()

        # Check access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(stream_url+'?project={}&virtual=1'.format(self.p1.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(data_url+'?filter={}'.format(stream_deserialized['slug']), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.get(stream_data_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()
