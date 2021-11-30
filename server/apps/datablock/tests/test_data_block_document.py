import datetime
import json

import dateutil.parser
from elasticsearch_dsl import Q

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from rest_framework import status

from apps.streamfilter.models import *
from apps.utils.test_util import TestMixin

from ..documents import *
from ..models import *

user_model = get_user_model()


class DeviceDocumentTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)


    def tearDown(self):
        Device.objects.all().delete()
        GenericProperty.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testLabelSearchDeviceObject(self):
        db1 = DataBlock.objects.create(org=self.o2, title='test', device=self.pd1, block=1, created_by=self.u1)
        db2 = DataBlock.objects.create(org=self.o2, title='dummy', device=self.pd2, block=1, created_by=self.u1)
        s = DataBlockDocument.search()
        s = s.query("match", title="test")
        qs = s.to_queryset()
        self.assertEqual(qs.count(), 1)

    def testProperties(self):
        db1 = DataBlock.objects.create(org=self.o2, title='test2', device=self.pd1, block=2, created_by=self.u1)

        s = DataBlockDocument.search()
        s = s.filter("nested",
            path="properties",
            query=Q({
                "bool" : {
                    "must" : [
                        Q("term", properties__key='prop1'),
                        Q("match", properties__value='4')
                    ]
                }
            })
        )
        qs = s.to_queryset()
        self.assertEqual(qs.count(), 0)

        GenericProperty.objects.create_int_property(slug=db1.slug,
                                                    created_by=self.u1,
                                                    name='prop1', value=4)
        GenericProperty.objects.create_str_property(slug=db1.slug,
                                                    created_by=self.u1,
                                                    name='prop2', value='4')
        GenericProperty.objects.create_bool_property(slug='b--0001-0000-0000-0002',
                                                     created_by=self.u1,
                                                     name='prop3', value=True)

        s = DataBlockDocument.search()
        s = s.filter("nested", 
            path="properties",
            query=Q({
                "bool" : {
                    "must" : [
                        Q("term", properties__key='prop1'),
                        Q("match", properties__value='4')
                    ]
                }
            })
        )
        qs = s.to_queryset()
        self.assertEqual(qs.count(), 1)
