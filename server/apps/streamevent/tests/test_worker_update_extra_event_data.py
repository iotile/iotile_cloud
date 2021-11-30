import json
import os

import dateutil.parser

from django.test import TestCase

from apps.physicaldevice.models import Device
from apps.sqsworker.exceptions import *
from apps.sqsworker.exceptions import WorkerActionHardError
from apps.stream.models import StreamId, StreamVariable
from apps.streamevent.models import StreamEventData
from apps.streamevent.worker.update_event_extra_data import UpdateEventExtraDataAction
from apps.utils.test_util import TestMixin


def _full_path(filename):
    module_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(module_path, 'data', 'reports', filename)


class UpdateEventExtraDataTestCase(TestMixin, TestCase):
    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=0x5001,
        )
        self.pd1 = Device.objects.create_device(id=0xa, project=self.p1, label='d1', template=self.dt1,
                                                created_by=self.u2)
        StreamId.objects.create_after_new_device(self.pd1)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()

    def tearDown(self):
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testWriteExtraEventData(self):
        action = UpdateEventExtraDataAction()
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        data = StreamEventData.objects.create(
            timestamp=t0,
            device_timestamp=10,
            stream_slug='s--0000-0001--0000-0000-0000-0001--0001',
            streamer_local_id=1
        )

        args = {
            "uuid": str(data.uuid),
            "extra_data": json.dumps({"max_x": 10})
        }
        self.assertIsNone(data.extra_data)
        action.execute(args)
        data = StreamEventData.objects.get(uuid=str(data.uuid))
        self.assertEqual(data.extra_data, {"max_x": 10})


    def testUpdateExtraEventData(self):
        action = UpdateEventExtraDataAction()
        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        data = StreamEventData.objects.create(
            timestamp=t0,
            device_timestamp=10,
            stream_slug='s--0000-0001--0000-0000-0000-0001--0001',
            streamer_local_id=1,
            extra_data={"a": 1, "b": 2}
        )

        args = {
            "uuid": str(data.uuid),
            "extra_data": json.dumps({"a": "a", "c": 3})
        }
        action.execute(args)
        data = StreamEventData.objects.get(uuid=str(data.uuid))
        self.assertEqual(data.extra_data, {"a": "a", "b": 2, "c": 3})

    def testExceptions(self):
        missing_args = {
            "uuid": "dummy_uuid"
        }
        action = UpdateEventExtraDataAction()

        with self.assertRaises(WorkerActionHardError) as context:
            action.execute(missing_args)
        self.assertEqual(str(context.exception), 'Missing fields in argument payload.\nReceived args: {}\nRequired args fields: uuid and extra_data'.format(missing_args))

        bad_uuid = {
            "uuid": "dummy",
            "extra_data": ""
        }

        with self.assertRaises(WorkerActionHardError) as context:
            action.execute(bad_uuid)
        self.assertEqual(str(context.exception), "{} is not a valid uuid format".format(bad_uuid['uuid']))

        non_exist_uuid = {
            "uuid": "123e4567-e89b-12d3-a456-426655440000",
            "extra_data": ""
        }

        with self.assertRaises(WorkerActionHardError):
            action.execute(non_exist_uuid)

        t0 = dateutil.parser.parse('2016-09-28T10:00:00Z')
        data = StreamEventData.objects.create(
            timestamp=t0,
            device_timestamp=10,
            stream_slug='s--0000-0001--0000-0000-0000-0001--0001',
            streamer_local_id=1
        )

        bad_extra = {
            "uuid": str(data.uuid),
            "extra_data": "not_json_string"
        }

        with self.assertRaises(WorkerActionHardError):
            action.execute(bad_extra)
