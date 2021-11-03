from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.physicaldevice.models import Device
from apps.utils.test_util import TestMixin

from ..forms import GenericPropertyForm
from ..models import GenericProperty

user_model = get_user_model()


class GenericProperyTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        GenericProperty.objects.all().delete()
        self.orgTestTearDown()
        self.userTestTearDown()
        self.deviceTemplateTestTearDown()

    def testBasics(self):
        prop1 = GenericProperty.objects.create_int_property(slug='d--0000-0000-0001-0001',
                                                            created_by=self.u1,
                                                            name='prop1', value=4)
        self.assertEqual(prop1.str_value, '4')
        self.assertEqual(prop1.type, 'int')
        self.assertEqual(prop1.value, 4)
        self.assertFalse(prop1.is_system)

        prop2 = GenericProperty.objects.create_str_property(slug='d--0000-0000-0001-0001',
                                                            created_by=self.u1,
                                                            name='prop2', value='4')
        self.assertEqual(prop2.str_value, '4')
        self.assertEqual(prop2.type, 'str')
        self.assertEqual(prop2.value, '4')
        self.assertFalse(prop2.is_system)

        prop3 = GenericProperty.objects.create_bool_property(slug='d--0000-0000-0001-0001',
                                                             created_by=self.u1,
                                                             name='prop3', value=True)
        self.assertEqual(prop3.str_value, 'True')
        self.assertEqual(prop3.type, 'bool')
        self.assertEqual(prop3.value, True)
        self.assertFalse(prop3.is_system)

        prop4 = GenericProperty.objects.create_bool_property(slug='d--0000-0000-0001-0001',
                                                             created_by=self.u1,
                                                             name='prop4', value=False)
        self.assertEqual(prop4.str_value, 'False')
        self.assertEqual(prop4.type, 'bool')
        self.assertEqual(prop4.value, False)

    def testSystemProperties(self):
        d = Device.objects.create(id=1, project=self.p1, template=self.dt1, created_by=self.u2)

        prop1 = GenericProperty.objects.create_int_property(slug=d.slug,
                                                            created_by=self.u1, is_system=True,
                                                            name='prop1', value=4)
        self.assertTrue(prop1.is_system)

        prop2 = GenericProperty.objects.create_str_property(slug=d.slug,
                                                            created_by=self.u1, is_system=True,
                                                            name='prop2', value='4')
        self.assertTrue(prop2.is_system)

        prop3 = GenericProperty.objects.create_bool_property(slug=d.slug,
                                                             created_by=self.u1, is_system=True,
                                                             name='prop3', value=True)
        self.assertTrue(prop3.is_system)

        prop4 = GenericProperty.objects.create_bool_property(slug=d.slug,
                                                             created_by=self.u1, is_system=False,
                                                             name='prop4', value=False)
        self.assertFalse(prop4.is_system)

        qs = GenericProperty.objects.object_properties_qs(d)
        self.assertEqual(qs.count(), 4)
        qs = GenericProperty.objects.object_properties_qs(d, is_system=True)
        self.assertEqual(qs.count(), 3)
        qs = GenericProperty.objects.object_properties_qs(d, is_system=False)
        self.assertEqual(qs.count(), 1)

    def testSetFunctions(self):
        p = GenericProperty.objects.create(target='d--0000-0000-0001-0001', created_by=self.u1, name='prop1')
        p.set_str_value('4')
        self.assertEqual(p.str_value, '4')
        self.assertEqual(p.type, 'str')
        self.assertEqual(p.value, '4')

        p.set_int_value(4)
        self.assertEqual(p.str_value, '4')
        self.assertEqual(p.type, 'int')
        self.assertEqual(p.value, 4)

        p.set_bool_value(True)
        self.assertEqual(p.str_value, 'True')
        self.assertEqual(p.type, 'bool')
        self.assertTrue(p.value)

    def testQueries(self):
        GenericProperty.objects.create_int_property(
            slug='d--0000-0000-0000-0001', created_by=self.u1, name='prop1', value=4
        )
        GenericProperty.objects.create_str_property(
            slug='d--0000-0000-0000-0001', created_by=self.u1, name='prop2', value='4'
        )
        GenericProperty.objects.create_bool_property(
            slug='d--0000-0000-0000-0002', created_by=self.u1, name='prop3', value=True
        )
        d1 = Device.objects.create(id=1, project=self.p1, template=self.dt1, created_by=self.u2)

        qs = GenericProperty.objects.object_properties_qs(d1)
        self.assertEqual(qs.count(), 2)
        self.assertEqual(qs.first().name, 'prop1')
        self.assertEqual(qs.last().name, 'prop2')

    def testValue(self):
        GenericProperty.objects.create_int_property(
            slug='d--0000-0000-0000-0001', created_by=self.u1, name='prop1', value=4
        )
        prop2 = GenericProperty.objects.create_str_property(
            slug='d--0000-0000-0000-0001', created_by=self.u1, name='prop2', value='4'
        )
        GenericProperty.objects.create_bool_property(
            slug='d--0000-0000-0000-0002', created_by=self.u1, name='prop3', value=True
        )
        d1 = Device.objects.create(id=1, project=self.p1, template=self.dt1, created_by=self.u2)

        p = GenericProperty.objects.object_property(d1, 'prop2')
        self.assertEqual(p, prop2)

    def testLargeString(self):
        p = GenericProperty.objects.create(target='d--0000-0000-0001-0001', created_by=self.u1, name='prop1')
        value = 'a' * 300
        self.assertEqual(len(value), 300)
        p.set_str_value(value)
        self.assertEqual(p.str_value, value[0:255])

    def testGenericPropertyForm(self):
        form_data = {
            'name': 'P1',
            'type': 'int',
            'str_value': 'wrong'
        }
        form = GenericPropertyForm(data=form_data)
        self.assertFalse(form.is_valid())
        form_data = {
            'name': 'P1',
            'type': 'int',
            'str_value': ''
        }
        form = GenericPropertyForm(data=form_data)
        self.assertFalse(form.is_valid())
        form_data = {
            'name': 'P1',
            'type': 'int',
            'str_value': 42
        }
        form = GenericPropertyForm(data=form_data)
        self.assertTrue(form.is_valid())
        form_data = {
            'name': 'P1',
            'type': 'bool',
            'str_value': 'wrong'
        }
        form = GenericPropertyForm(data=form_data)
        self.assertFalse(form.is_valid())
        form_data = {
            'name': 'P1',
            'type': 'bool',
            'str_value': ''
        }
        form = GenericPropertyForm(data=form_data)
        self.assertFalse(form.is_valid())
        form_data = {
            'name': 'P1',
            'type': 'bool',
            'str_value': 'True'
        }
        form = GenericPropertyForm(data=form_data)
        self.assertTrue(form.is_valid())
        form_data = {
            'name': 'P1',
            'type': 'str',
            'str_value': 'correct'
        }
        form = GenericPropertyForm(data=form_data)
        self.assertTrue(form.is_valid())
