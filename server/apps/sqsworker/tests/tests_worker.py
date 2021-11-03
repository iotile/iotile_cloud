import json
import os
import datetime
import dateutil.parser
import copy
import random
import string
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django.core.cache import cache
from django.urls import reverse

from rest_framework import status

from apps.utils.test_util import TestMixin
from apps.stream.models import StreamVariable, StreamId
from apps.streamdata.models import StreamData
from apps.physicaldevice.models import Device
from apps.utils.timezone_utils import *
from apps.streamer.models import Streamer, StreamerReport
from apps.utils.dynamic_loading import str_to_class
from ..action import Action
from ..workerhelper import Worker
from ..tracker import WorkerUUID
from ..common import ACTION_CLASS_MODULE

user_model = get_user_model()


class TestWorkerAction(Action):
    def execute(self, arguments):
        super(TestWorkerAction, self).execute(arguments)
        if 'message' in arguments:
            s = StreamId.objects.all().first()
            StreamData.objects.create(
                stream_slug=s.slug,
                type='Num',
                streamer_local_id=1,
                timestamp=timezone.now(),
                int_value=5
            )
        else:
            raise Exception('Missing arguments')


class Message:
    message_id = None
    message_attributes = {}
    attributes = {}
    body = None
    queue = None

    def __init__(self, queue, body, message_attributes=None, attributes=None):
        self.queue = queue
        self.message_id = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(5))
        self.message_attributes = message_attributes
        self.attributes = attributes
        self.body = json.dumps(body)

    def delete(self):
        self.queue.delete(self.message_id)


class QueueTestMock:
    messages = []

    def __init__(self):
        self.messages = []

    def receive_messages(self, MaxNumberOfMessages):
        if len(self.messages) > MaxNumberOfMessages:
            return self.messages[:MaxNumberOfMessages]
        return copy.deepcopy(self.messages)

    def add_messages(self, messages_body_list):
        for msg_body in messages_body_list:
            self.messages += [Message(self, msg_body)]

    def delete(self, message_id):
        for message in self.messages:
            if message.message_id == message_id:
                self.messages.remove(message)
                break

    def delete_all(self):
        self.messages = []


class WorkerTestCase(TestMixin, TestCase):
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
        self.pd1 = Device.objects.create_device(id=0xa, project=self.p1, label='d1', template=self.dt1,
                                                created_by=self.u2)
        self.pd2 = Device.objects.create_device(id=0xb, project=self.p2, label='d2', template=self.dt1,
                                                created_by=self.u3)
        StreamId.objects.create_after_new_device(self.pd1)
        StreamId.objects.create_after_new_device(self.pd2)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()
        self.s2 = StreamId.objects.filter(variable=self.v2).first()

        self.admin = user_model.objects.create_superuser(username='admin', email='admin@acme.com', password='pass')
        self.admin.is_active = True
        self.admin.save()
        self.assertTrue(self.admin.is_admin)
        self.assertTrue(self.admin.is_staff)

        self.staff = user_model.objects.create_user(username='staff', email='staff@acme.com', password='pass')
        self.staff.is_active = True
        self.staff.is_admin = False
        self.staff.is_staff = True
        self.staff.save()

        self.user = user_model.objects.create_user(username='user', email='user@acme.com', password='pass')
        self.user.is_active = True
        self.user.is_admin = False
        self.user.is_staff = False
        self.user.save()

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

    def testActionModules(self):
        for key in ACTION_CLASS_MODULE.keys():
            item = ACTION_CLASS_MODULE[key]
            action_class = str_to_class(item['module'], item['class'])
            self.assertEqual(item['class'], action_class.__name__)

    def testWorkerId(self):
        id = WorkerUUID.get_singleton()
        ts_now = timezone.now()
        id.start(ts_now)
        self.assertIsNotNone(id.id)
        self.assertEqual(str(id), str(id.id))
        self.assertEqual(id.info_key, 'worker-info:{}'.format(str(id.id)))
        self.assertEqual(id.count_key, 'worker-count:{}'.format(str(id.id)))
        if cache:
            self.assertEqual(id.count, 0)
            id.increment_count()
            id.increment_count()
            self.assertEqual(id.count, 2)
            info = id.info
            self.assertIsNotNone(info)
            self.assertTrue('start_dt' in info)
            self.assertEqual(info['uuid'], str(id))
            self.assertEqual(info['start_dt'], ts_now)

            self.assertEqual(id.action_count('WorkerStarted'), 0)
            id.increment_action_count('WorkerStarted')
            self.assertEqual(id.action_count('WorkerStarted'), 1)

        id2 = WorkerUUID.get_singleton()
        self.assertEqual(str(id), str(id2))

    def testQueueLoop(self):
        queue = QueueTestMock()
        queue.add_messages([
            {
                "module": "apps.sqsworker.tests",
                "class": "TestWorkerAction",
                "arguments": {
                    "message": "Hello worker"
                }
            },
            {
                "module": "apps.sqsworker.tests",
                "class": "TestWorkerAction",
                "arguments": {
                    "not_message": "Hello worker"
                }
            }
        ])
        self.assertEqual(StreamData.objects.all().count(), 0)
        worker = Worker(queue, 2)
        worker.run_once_without_delete()
        self.assertEqual(StreamData.objects.all().count(), 1)

    @mock.patch('apps.sqsworker.views.WorkerStats')
    def testAccessControls(self, mock_worker_stats):
        mock_worker_stats.return_value = {}

        url_list = [
            reverse('staff:worker:home'),
            reverse('staff:worker:schedule'),
            reverse('staff:worker:cleanup-all'),
            reverse('staff:worker:action-detail', kwargs={'action_name': 'ProcessReportAction'}),
        ]
        for url in url_list:
            response = self.client.get(url)
            self.assertRedirects(response, '/account/login/?next={0}'.format(url))

            ok = self.client.login(email='admin@acme.com', password='pass')
            self.assertTrue(ok)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.client.logout()

            ok = self.client.login(email='staff@acme.com', password='pass')
            self.assertTrue(ok)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.client.logout()

            ok = self.client.login(email='user@acme.com', password='pass')
            self.assertTrue(ok)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

            self.client.logout()
