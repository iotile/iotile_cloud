import json
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()


class GenericProperyTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        ConfigAttribute.objects.all().delete()
        ConfigAttributeName.objects.all().delete()
        self.orgTestTearDown()
        self.userTestTearDown()
        self.deviceTemplateTestTearDown()

    def testAutoConfigName(self):
        self.assertEqual(ConfigAttributeName.objects.count(), 0)

        name = ConfigAttribute.objects._config_name(':foo')
        self.assertIsNone(name)

        name = ConfigAttribute.objects._config_name(':foo', updated_by=self.u1)
        self.assertIsNotNone(name)
        self.assertEqual(ConfigAttributeName.objects.count(), 1)

        name = ConfigAttribute.objects._config_name(':foo')
        self.assertIsNotNone(name)
        self.assertEqual(ConfigAttributeName.objects.count(), 1)
        self.assertEqual(str(name), ':foo')

        name = ConfigAttributeName.objects.first()
        self.assertEqual(str(name), ':foo')

    def testBasicConfigAttribute(self):
        self.assertEqual(ConfigAttributeName.objects.count(), 0)
        self.assertEqual(ConfigAttribute.objects.count(), 0)
        attr1 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.o2,
            name=':report:trip-summary:temp-range',
            data={
                'below': 17,
                'above': 30,
                'units': 'C'
            },
            updated_by=self.u1
        )
        self.assertEqual(str(attr1), '^org-1::report:trip-summary:temp-range')
        self.assertEqual(attr1.obj.slug, self.o2.slug)

        self.assertEqual(ConfigAttributeName.objects.count(), 1)
        self.assertEqual(ConfigAttribute.objects.count(), 1)
        name = ConfigAttributeName.objects.first()
        self.assertEqual(str(name), ':report:trip-summary:temp-range')
        self.assertEqual(attr1.name.id, name.id)

    def testMultiplePerTarget(self):
        self.assertEqual(ConfigAttributeName.objects.count(), 0)
        self.assertEqual(ConfigAttribute.objects.count(), 0)
        foo_attr1 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.o2,
            name=':foo',
            data={'a': 'b'},
            updated_by=self.u1
        )
        foo_attr2 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.o2,
            name=':bar',
            data={'a': 'b'},
            updated_by=self.u1
        )
        foo_attr3 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.o3,
            name=':bar',
            data={'a': 'c'},
            updated_by=self.u1
        )
        foo_attr4 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.u3,
            name=':user',
            data={'a': 'c'},
            updated_by=self.u1
        )
        self.assertEqual(ConfigAttributeName.objects.count(), 3)
        self.assertEqual(ConfigAttribute.objects.count(), 4)

    def testManagerGets(self):
        name = ConfigAttributeName.objects.create(name=':foo', created_by=self.u1)
        config1 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.o2,
            name=name,
            data={'a': 'b'},
            updated_by=self.u1
        )
        self.assertEqual(config1.data['a'], 'b')
        self.assertEqual(ConfigAttribute.objects.count(), 1)
        config2 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.o2,
            name=name,
            data={'a': 'c'},
            updated_by=self.u1
        )
        self.assertEqual(ConfigAttribute.objects.count(), 1)
        self.assertEqual(config2, ConfigAttribute.objects.first())
        self.assertEqual(config2.data['a'], 'c')

        config3 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.o2,
            name=':bar',
            data={'a': 5},
            updated_by=self.u1
        )

        obj = ConfigAttribute.objects.get_attribute(target=self.o2, name=':bar')
        self.assertEqual(obj.id, config3.id)

        qs = ConfigAttribute.objects.qs_by_target(self.o2)
        self.assertEqual(qs.count(), 2)
        first = qs.first()
        self.assertEqual(str(first.name), ':bar')
        last = qs.last()
        self.assertEqual(str(last.name), ':foo')

    def testPrioritySearchPath(self):
        project = Project.objects.create(name='Project 2', org=self.o2, created_by=self.u2)

        foo_name = ConfigAttributeName.objects.create(name=':foo', created_by=self.u1)
        bar_name = ConfigAttributeName.objects.create(name=':bar', created_by=self.u1)
        foo_attr1 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.o2,
            name=foo_name,
            data={'a': 'b'},
            updated_by=self.u1
        )
        foo_attr2 = ConfigAttribute.objects.get_or_create_attribute(
            target=self.u1,
            name=foo_name,
            data={'a': 'b'},
            updated_by=self.u1
        )
        bar_attr = ConfigAttribute.objects.get_or_create_attribute(
            target=self.u2,
            name=bar_name,
            data={'c': 'd'},
            updated_by=self.u2
        )

        attr = ConfigAttribute.objects.get_attribute_by_priority(
            target_slug=project.obj_target_slug,
            name=foo_name
        )
        self.assertEqual(attr.id, foo_attr1.id)

        attr = ConfigAttribute.objects.get_attribute_by_priority(
            target_slug=project.obj_target_slug,
            name=bar_name
        )
        self.assertIsNone(attr)

        attr = ConfigAttribute.objects.get_attribute_by_priority(
            target_slug=project.obj_target_slug,
            name=bar_name,
            user=self.u1
        )
        self.assertIsNone(attr)

        attr = ConfigAttribute.objects.get_attribute_by_priority(
            target_slug=project.obj_target_slug,
            name=bar_name,
            user=self.u2
        )
        self.assertEqual(attr.id, bar_attr.id)

        foo_attr1.delete()
        attr = ConfigAttribute.objects.get_attribute_by_priority(
            target_slug=project.obj_target_slug,
            name=foo_name,
            user=self.u1
        )
        self.assertEqual(attr.id, foo_attr2.id)
