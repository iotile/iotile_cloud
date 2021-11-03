from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.reverse import reverse
from rest_framework import status

from apps.utils.test_util import TestMixin
from apps.utils.gid.convert import *
from apps.property.models import GenericProperty


from ..models import *
from ..documents import *

from elasticsearch_dsl import Q

user_model = get_user_model()


class DeviceDocumentTestCase(TestMixin, TestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        GenericProperty.objects.all().delete()
        Device.objects.all().delete()
        self.orgTestTearDown()
        self.userTestTearDown()
        self.deviceTemplateTestTearDown()

    def testLabelSearchDeviceObject(self):
        pd1 = Device.objects.create(id=3, project=self.p1, label='test-label', template=self.dt1, created_by=self.u2)
        pd2 = Device.objects.create(id=4, project=self.p2, label='d2', template=self.dt1, created_by=self.u3)
        s = DeviceDocument.search()
        s = s.query("match", label="test-label")
        qs = s.to_queryset()
        self.assertEqual(qs.count(), 1)

    def testSearchProperties(self):
        d1 = Device.objects.create(id=0x100, project=self.p1, org=self.p1.org,
                                   template=self.dt1, created_by=self.u2)
        s = DeviceDocument.search()
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

        GenericProperty.objects.create_int_property(slug='d--0000-0000-0000-0100',
                                                    created_by=self.u1,
                                                    name='prop1', value=4)
        GenericProperty.objects.create_str_property(slug='d--0000-0000-0000-0100',
                                                    created_by=self.u1,
                                                    name='prop2', value='4')
        GenericProperty.objects.create_bool_property(slug='d--0000-0000-0000-0002',
                                                     created_by=self.u1,
                                                     name='prop3', value=True)

        s = DeviceDocument.search()
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
