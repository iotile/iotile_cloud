from django.test import TestCase
from django.contrib.auth import get_user_model

from rest_framework.reverse import reverse
from rest_framework import status

from apps.project.models import Project
from apps.utils.test_util import TestMixin
from apps.utils.gid.convert import formatted_gdid, int64gid, int2did
from apps.sensorgraph.models import SensorGraph
from apps.stream.models import StreamId, StreamVariable
from apps.property.models import GenericProperty
from apps.property.forms import GenericPropertyForm
from apps.org.models import Org

from ..models import Device

user_model = get_user_model()


class DeviceTestCase(TestMixin, TestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        GenericProperty.objects.all().delete()
        Device.objects.all().delete()
        StreamVariable.objects.all().delete()
        StreamId.objects.all().delete()
        self.orgTestTearDown()
        self.userTestTearDown()
        self.deviceTemplateTestTearDown()

    def testDeviceId(self):
        self.assertEqual(formatted_gdid('0001'), 'd--0000-0000-0000-0001')
        self.assertEqual(formatted_gdid('0000-0001'), 'd--0000-0000-0000-0001')
        self.assertEqual(formatted_gdid('0000-0000-0001'), 'd--0000-0000-0000-0001')
        self.assertEqual(formatted_gdid('0000-0000-0000-0001'), 'd--0000-0000-0000-0001')

        self.assertEqual(int2did(1), '0000-0000-0000-0001')
        self.assertEqual(int2did(1024), '0000-0000-0000-0400')
        self.assertEqual(int2did(65536), '0000-0000-0001-0000')

    def testBasicDeviceObject(self):
        pd1 = Device.objects.create(id=1, project=self.p1, template=self.dt1, created_by=self.u2)
        self.assertEqual(pd1.formatted_gid, int64gid(pd1.id))
        self.assertEqual(str(pd1), formatted_gdid(pd1.formatted_gid))
        pd1.save()
        pd2 = Device.objects.create(id=2, project=self.p1, template=self.dt1, created_by=self.u2)
        pd2.save()

        self.assertEqual(Device.objects.count(), 2)
        self.assertEqual(str(pd1), 'd--0000-0000-0000-0001')
        self.assertEqual(str(pd2), 'd--0000-0000-0000-0002')

        other_slug = pd2.get_stream_slug_for('9999')
        self.assertEqual(str(other_slug), 's--{0}--{1}--9999'.format(self.p1.formatted_gid, pd2.formatted_gid))

    def testManagerCreate(self):
        device = Device.objects.create_device(
            label='D1', project=self.p1, template=self.dt1, created_by=self.u2,
        )
        self.assertIsNotNone(device)
        self.assertEqual(device.org, self.p1.org)
        self.assertEqual(device.label, 'D1')
        self.assertEqual(Device.objects.count(), 1)

        device = Device.objects.create_device(
            label='D2', project=self.p1, created_by=self.u2,
            template=self.dt1, external_id='aa'
        )
        self.assertIsNotNone(device)
        self.assertEqual(device.external_id, 'aa')

        with self.assertRaises(AssertionError):
            Device.objects.create_device(
                label='d3', project=None, template=self.dt1, created_by=self.u2, foo=1
            )

    def testHasAccess(self):
        pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)
        self.assertTrue(pd1.has_access(self.u1))
        self.assertTrue(pd1.has_access(self.u2))
        self.assertFalse(pd1.has_access(self.u3))
        self.assertTrue(pd2.has_access(self.u1))
        self.assertFalse(pd2.has_access(self.u2))
        self.assertTrue(pd2.has_access(self.u3))
        self.o2.register_user(self.u3)
        self.assertTrue(self.o2.is_member(self.u3))
        self.assertTrue(self.o2.has_access(self.u3))
        self.assertTrue(pd1.has_access(self.u3))
        self.assertTrue(pd1.has_access(self.u3))

    def testManager(self):
        Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        d2 = Device.objects.create_device(project=self.p2, template=self.dt1, created_by=self.u3)
        self.assertEqual(Device.objects.user_device_qs(self.u2).count(), 1)
        self.assertEqual(Device.objects.user_device_qs(self.u3).count(), 1)
        self.assertEqual(Device.objects.user_device_qs(self.u2, self.p1).count(), 1)
        self.assertEqual(Device.objects.user_device_qs(self.u3, self.p2).count(), 1)
        self.assertEqual(Device.objects.user_device_qs(self.u2, self.p2).count(), 0)
        self.assertEqual(Device.objects.project_device_qs(self.p1).count(), 1)
        d2.active=False
        d2.save()
        self.assertEqual(Device.objects.user_device_qs(self.u3).count(), 0)
        self.assertEqual(Device.objects.user_device_qs(self.u3, all=True).count(), 1)
        self.assertEqual(Device.objects.project_device_qs(self.p2).count(), 0)
        self.assertEqual(Device.objects.project_device_qs(self.p2, all=True).count(), 1)

    def testDeviceIsNotDeleted(self):
        u = user_model.objects.create_user(username='user4', email='user4@foo.com', password='pass')
        u.is_active = True
        u.save()
        sg1 = SensorGraph.objects.create(name='SG 1',
                                         major_version=1,
                                         created_by=self.u1, org=self.o1)
        o = Org.objects.create_org(name='Org 4', created_by=u)
        p = Project.objects.create(name='Project 4', project_template=self.pt1, created_by=u, org=o)
        Device.objects.create_device(project=p, template=self.dt1, sg=sg1, created_by=self.u1)
        Device.objects.create_device(project=None, template=self.dt1, sg=sg1, created_by=self.u1)
        self.assertEqual(Device.objects.count(), 2)
        p.delete()
        self.assertEqual(Device.objects.count(), 2)
        u.delete()
        self.assertEqual(Device.objects.count(), 2)
        self.dt1.delete()
        self.assertEqual(Device.objects.count(), 2)
        sg1.delete()
        self.assertEqual(Device.objects.count(), 2)

    def testProperties(self):
        GenericProperty.objects.create_int_property(slug='d--0000-0000-0000-0100',
                                                    created_by=self.u1,
                                                    name='prop1', value=4)
        GenericProperty.objects.create_str_property(slug='d--0000-0000-0000-0100',
                                                    created_by=self.u1,
                                                    name='prop2', value='4')
        GenericProperty.objects.create_bool_property(slug='d--0000-0000-0000-0002',
                                                     created_by=self.u1,
                                                     name='prop3', value=True)
        d1 = Device.objects.create(id=0x100, project=self.p1, org=self.p1.org,
                                   template=self.dt1, created_by=self.u2)

        qs = d1.get_properties_qs()
        self.assertEqual(qs.count(), 2)
        self.assertEqual(qs.first().name, 'prop1')
        self.assertEqual(qs.last().name, 'prop2')

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        url = reverse('org:project:device:property', kwargs={'org_slug':self.p1.org.slug, 'project_id': self.p1.id, 'pk': d1.id} )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'IOTile Device Property Info')
        self.assertContains(response, qs.first().id)
        self.assertContains(response, qs.last().id)
        self.assertContains(response, qs.first().name)
        self.assertContains(response, qs.last().name)
        self.assertContains(response, qs.first().value)
        self.assertContains(response, qs.last().value)

        self.client.logout()

    def testCreateDeviceProperty(self):
        d1 = Device.objects.create(id=0x100, project=self.p1, template=self.dt1, created_by=self.u2)
        d1.org = self.p1.org
        d1.save()

        qs = GenericProperty.objects.object_properties_qs(d1)
        self.assertEqual(qs.count(), 0)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {'name' : 'new prop',
                   'type' : 'int',
                   'str_value' : 5}

        add_url = reverse('property:add', kwargs={'target_slug': d1.slug} )
        response = self.client.get(add_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(add_url, payload)
        url = reverse('org:project:device:property', kwargs={'org_slug':self.p1.org.slug, 'project_id': self.p1.id, 'pk': d1.id} )
        self.assertRedirects(response, expected_url=url, status_code=302, target_status_code=200)
        response = self.client.get(url)

        qs = GenericProperty.objects.object_properties_qs(d1)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().name, 'new prop')
        self.assertEqual(qs.first().value, 5)
        self.assertContains(response, 'IOTile Device Property Info')
        self.assertContains(response, 'new prop')
        self.assertContains(response, '5')

        payload = {'name' : 'new prop',
                   'type' : 'str',
                   'is_system': True,
                   'str_value' : 'acceleration'}

        add_url = reverse('property:add', kwargs={'target_slug': d1.slug} )
        response = self.client.get(add_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Can't have duplicate object / property name pairs
        self.assertContains(response, "Add IOTile Property")
        form = GenericPropertyForm(data=payload)
        form.target_slug = d1.slug
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['name'], ["Property with name \"{}\" already exists".format(payload['name'])])
        qs = GenericProperty.objects.object_properties_qs(d1)
        self.assertEqual(qs.count(), 1)

        url = reverse('org:project:device:property', kwargs={'org_slug':self.p1.org.slug, 'project_id': self.p1.id, 'pk': d1.id} )
        response = self.client.get(url)

        qs = GenericProperty.objects.object_properties_qs(d1)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().name, 'new prop')
        self.assertEqual(qs.first().value, 5)
        self.assertContains(response, 'IOTile Device Property Info')
        self.assertContains(response, 'new prop')
        self.assertContains(response, '5')

        # Check bool validation
        payload = {'name' : 'invalid bool prop',
                   'type' : 'bool',
                   'str_value' : 'acceleration'}

        add_url = reverse('property:add', kwargs={'target_slug': d1.slug} )
        response = self.client.get(add_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Add IOTile Property")
        form = GenericPropertyForm(data=payload)
        self.assertEqual(form.errors['str_value'], ["Value must be either 'True' or 'False'"])
        qs = GenericProperty.objects.object_properties_qs(d1)
        self.assertEqual(qs.count(), 1)

        # Check int validation
        payload = {'name' : 'invalid int prop',
                   'type' : 'int',
                   'str_value' : 'acceleration'}

        add_url = reverse('property:add', kwargs={'target_slug': d1.slug} )
        response = self.client.get(add_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Add IOTile Property")
        form = GenericPropertyForm(data=payload)
        self.assertEqual(form.errors['str_value'], ["Value must be an Integer"])
        qs = GenericProperty.objects.object_properties_qs(d1)
        self.assertEqual(qs.count(), 1)

        self.client.logout()

    def testUpdateDeviceProperty(self):
        d1 = Device.objects.create(id=1, project=self.p1, template=self.dt1, created_by=self.u2)
        prop1 = GenericProperty.objects.create_int_property(slug='d--0000-0000-0000-0001',
                                                            created_by=self.u1,
                                                            name='prop1', value=2063)
        prop2 = GenericProperty.objects.create_str_property(slug='d--0000-0000-0000-0001',
                                                            created_by=self.u1,
                                                            name='prop2', value='5')
        d1.org = self.p1.org
        d1.save()

        qs = GenericProperty.objects.object_properties_qs(d1)
        self.assertEqual(qs.count(), 2)
        self.assertEqual(qs.first().name, 'prop1')
        self.assertEqual(qs.last().name, 'prop2')

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {'name' : 'new prop name',
                   'type' : 'int',
                   'is_system': True,
                   'str_value' : 5}

        url = reverse('org:project:device:property', kwargs={'org_slug':self.p1.org.slug, 'project_id': self.p1.id, 'pk': d1.id} )

        edit_url = (reverse('property:edit', kwargs={'target_slug': d1.slug, 'pk': prop1.id} ))
        response = self.client.get(edit_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(edit_url, payload)
        self.assertRedirects(response, expected_url=url, status_code=302, target_status_code=200)

        qs = GenericProperty.objects.object_properties_qs(d1)
        self.assertEqual(qs.count(), 2)

        response = self.client.get(url)
        self.assertContains(response, 'IOTile Device Property Info')
        self.assertContains(response, 'new prop name')
        self.assertContains(response, 5)
        self.assertContains(response, 'prop2')
        self.assertContains(response, '4')
        self.assertNotContains(response, 'prop1')
        self.assertNotContains(response, '2063')

        # name validator allows updating with the same name
        payload = {'name' : 'new prop name',
                   'type' : 'int',
                   'str_value' : 5567}

        url = reverse('org:project:device:property', kwargs={'org_slug':self.p1.org.slug, 'project_id': self.p1.id, 'pk': d1.id} )

        edit_url = (reverse('property:edit', kwargs={'target_slug': d1.slug, 'pk': prop1.id} ))
        response = self.client.get(edit_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(edit_url, payload)
        self.assertRedirects(response, expected_url=url, status_code=302, target_status_code=200)

        qs = GenericProperty.objects.object_properties_qs(d1)
        self.assertEqual(qs.count(), 2)

        response = self.client.get(url)
        self.assertContains(response, 'IOTile Device Property Info')
        self.assertContains(response, 'new prop name')
        self.assertContains(response, 5567)
        self.assertContains(response, 'prop2')
        self.assertContains(response, '4')


        payload = {'name' : 'prop2',
                   'type' : 'int',
                   'str_value' : 5}

        url = reverse('org:project:device:property', kwargs={'org_slug':self.p1.org.slug, 'project_id': self.p1.id, 'pk': d1.id} )

        edit_url = (reverse('property:edit', kwargs={'target_slug': d1.slug, 'pk': prop1.id} ))
        response = self.client.get(edit_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # No duplicate object / property name pairs
        with self.assertRaisesRegex(ValueError, "Property with this name already exists."):
            self.client.post(edit_url, payload)

        url = reverse('org:project:device:property', kwargs={'org_slug':self.p1.org.slug, 'project_id': self.p1.id, 'pk': d1.id} )
        response = self.client.get(url)

        qs = GenericProperty.objects.object_properties_qs(d1)
        self.assertEqual(qs.count(), 2)

        response = self.client.get(url)
        self.assertContains(response, 'IOTile Device Property Info')
        self.assertContains(response, 'new prop name')
        self.assertContains(response, 5567)
        self.assertContains(response, 'prop2')
        self.assertContains(response, '4')

        self.client.logout()

    def testDeleteDeviceProperty(self):
        prop1 = GenericProperty.objects.create_int_property(slug='d--0000-0000-0000-0001',
                                                            created_by=self.u1,
                                                            name='prop1', value=2063)
        prop2 = GenericProperty.objects.create_str_property(slug='d--0000-0000-0000-0001',
                                                            created_by=self.u1,
                                                            name='prop2', value='5')
        d1 = Device.objects.create(id=1, project=self.p1, template=self.dt1, created_by=self.u2)
        d1.org = self.p1.org
        d1.save()

        qs = GenericProperty.objects.object_properties_qs(d1)
        self.assertEqual(qs.count(), 2)
        self.assertEqual(qs.first().name, 'prop1')
        self.assertEqual(qs.last().name, 'prop2')

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {}
        url = reverse('org:project:device:property', kwargs={'org_slug':self.p1.org.slug, 'project_id': self.p1.id, 'pk': d1.id} )
        delete_url = (reverse('property:delete', kwargs={'target_slug': d1.slug, 'pk': prop1.id} ))
        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'Are you sure you want to delete property')
        response = self.client.post(delete_url, payload)
        self.assertRedirects(response, expected_url=url, status_code=302, target_status_code=200)

        qs = GenericProperty.objects.object_properties_qs(d1)
        self.assertEqual(qs.count(), 1)

        response = self.client.get(url)
        self.assertContains(response, 'IOTile Device Property Info')
        self.assertContains(response, 'prop2')
        self.assertContains(response, '4')
        self.assertNotContains(response, 'prop1')
        self.assertNotContains(response, '2063')

        self.client.logout()

    def testDevicePropertyMemberPermissions(self):
        """
        Test that people with no permissions cannot access
        """
        prop1 = GenericProperty.objects.create_int_property(slug='d--0000-0000-0000-0001',
                                                            created_by=self.u1,
                                                            name='prop1', value=2063)
        d1 = Device.objects.create(id=1, project=self.p1, template=self.dt1, created_by=self.u2)
        d1.org = self.p1.org
        d1.save()

        property_url = reverse('org:project:device:property',
                               kwargs={'org_slug':self.p1.org.slug, 'project_id': self.p1.id, 'pk': d1.id} )
        property_edit_url = (reverse('property:edit', kwargs={'target_slug': d1.slug, 'pk': prop1.id} ))
        property_delete_url = (reverse('property:delete', kwargs={'target_slug': d1.slug, 'pk': prop1.id} ))

        self.client.login(email='user3@foo.com', password='pass')

        membership = self.p1.org.register_user(self.u3, role='m1')
        membership.permissions['can_modify_device_properties'] = False
        membership.save()

        read_pages = []
        write_pages = [property_edit_url, property_delete_url]
        for page in read_pages:
            response = self.client.get(page)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        for page in write_pages:
            response = self.client.get(page)
            self.assertEqual(response.status_code, status.HTTP_302_FOUND)

        membership.permissions['can_modify_device_properties'] = True
        membership.permissions['can_read_device_properties'] = False
        membership.save()
        for page in write_pages:
            response = self.client.get(page)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        for page in read_pages:
            response = self.client.get(page)
            self.assertEqual(response.status_code, status.HTTP_302_FOUND)

        self.client.logout()

    def testDeviceMemberPermissions(self):
        """
        Test that people with no permissions cannot access
        """
        d1 = Device.objects.create(id=1, project=self.p1, template=self.dt1, created_by=self.u2)
        d1.org = self.p1.org
        d1.save()

        read_pages = [
            reverse('org:project:device:detail', args=(d1.org.slug, str(self.p1.id), d1.id,)),
            reverse('org:project:device:health-status', args=(d1.org.slug, str(self.p1.id), d1.id,)),
        ]
        write_pages = [
            reverse('org:project:device:edit', args=(d1.org.slug, str(self.p1.id), d1.id,)),
            reverse('org:project:device:move', args=(d1.org.slug, str(self.p1.id), d1.id,)),
            reverse('org:project:device:reset', args=(d1.org.slug, str(self.p1.id), d1.id,)),
            reverse('org:project:device:trim', args=(d1.org.slug, str(self.p1.id), d1.id,)),
            reverse('org:project:device:health-settings', args=(d1.org.slug, str(self.p1.id), d1.id,)),
        ]

        self.client.login(email='user3@foo.com', password='pass')

        membership = self.p1.org.register_user(self.u3, role='m1')
        membership.permissions['can_reset_device'] = False
        membership.permissions['can_modify_device'] = False
        membership.permissions['can_access_classic'] = True
        membership.save()

        for page in write_pages:
            response = self.client.get(page)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, msg=page)
        for page in read_pages:
            response = self.client.get(page)
            self.assertEqual(response.status_code, status.HTTP_200_OK, msg=page)

        membership.permissions['can_reset_device'] = True
        membership.permissions['can_modify_device'] = True
        membership.permissions['can_access_classic'] = False
        membership.save()

        for page in write_pages:
            response = self.client.get(page)
            self.assertEqual(response.status_code, status.HTTP_200_OK, msg=page)
        for page in read_pages:
            response = self.client.get(page)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, msg=page)

        self.client.logout()
