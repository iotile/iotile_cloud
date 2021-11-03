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


class StreamSystemVariableTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.projectTemplateTestSetup()

    def tearDown(self):
        self.projectTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def test_system_variables(self):
        self.assertEqual(ProjectTemplate.objects.count(), 2)
        self.assertEqual(Project.objects.count(), 4)
        self.assertEqual(StreamVariable.objects.count(), 2)
        sv1 = StreamSystemVariable.objects.create(project=self.pt1_project, variable=self.v0)
        self.assertEqual(StreamSystemVariable.objects.count(), 1)

        qs = StreamSystemVariable.project_system_variables(self.pt1_project)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), sv1)
        qs = StreamSystemVariable.project_system_variables(self.p1)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), sv1)


