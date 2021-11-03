import json
import datetime
import dateutil.parser
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.physicaldevice.models import Device
from apps.utils.test_util import TestMixin
from apps.utils.gid.convert import *

from apps.property.models import GenericProperty
from apps.stream.models import StreamVariable, StreamId
from apps.physicaldevice.models import Device
from apps.streamfilter.models import *
from apps.utils.gid.convert import formatted_dbid

from ..models import *
from ..worker.archive_device_data import ArchiveDeviceDataAction

user_model = get_user_model()


class DataBlockTests(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=1,
        )
        self.v2 = StreamVariable.objects.create_variable(
            name='Var B', project=self.p2, created_by=self.u3, lid=2,
        )
        self.sg1 = SensorGraph.objects.create(name='SG 1', major_version=1, created_by=self.u2, org=self.o1)
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', sg=self.sg1, template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)
        self.pd3 = Device.objects.create_device(project=self.p2, label='d3', template=self.dt1, created_by=self.u3)
        StreamId.objects.create_after_new_device(self.pd1)
        StreamId.objects.create_after_new_device(self.pd2)
        self.s1 = StreamId.objects.filter(variable=self.v1).first()
        self.s2 = StreamId.objects.filter(variable=self.v2).first()

    def tearDown(self):
        StreamFilterAction.objects.all().delete()
        StreamFilterTrigger.objects.all().delete()
        StreamFilter.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasicGetAccess(self):
        bid = formatted_dbid(did=self.pd1.formatted_gid, bid='0001')
        url = reverse('datablock-list')
        detail_url = reverse('datablock-detail', kwargs={'slug': bid})
        extra_url = reverse('datablock-extra', kwargs={'slug': bid})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        db1 = DataBlock.objects.create(org=self.o2, title='test', device=self.pd1, block=1, created_by=self.u2)
        db2 = DataBlock.objects.create(org=self.o2, title='some test', device=self.pd2, block=2, created_by=self.u2)
        db3 = DataBlock.objects.create(org=self.o1, title='test', device=self.pd1, block=3, created_by=self.u1)
        db4 = DataBlock.objects.create(org=self.o1, title='test', device=self.pd1, block=4, created_by=self.u1)
        db5 = DataBlock.objects.create(org=self.o1, title='some test', device=self.pd1, block=5, created_by=self.u1)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 3)

        resp = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 5)

        resp = self.client.get(url+'?staff=1&org={}'.format(self.o2.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        resp = self.client.get(url+'?staff=1&device={}'.format(self.pd1.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)

        resp = self.client.get(url+'?staff=1&org={}&q=some'.format(self.o1.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], bid)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertTrue(self.o2.has_access(self.u2))
        self.assertTrue(self.pd1.has_access(self.u2))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], bid)

        resp = self.client.get(extra_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], bid)
        self.assertTrue('stream_counts' in deserialized)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)
        self.assertFalse(self.o2.has_access(self.u3))
        self.assertFalse(self.pd1.has_access(self.u3))

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        resp = self.client.get(detail_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.p1.org.register_user(self.u3, role='r1')
        self.assertFalse(self.p1.org.has_permission(self.u3, 'can_access_datablock'))

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testDatatable(self):
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)
        url = reverse('datablock-datatable')

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['recordsTotal'], 0)

        db1 = DataBlock.objects.create(org=self.o2, title='test', device=self.pd1, block=1, created_by=self.u2)
        db2 = DataBlock.objects.create(org=self.o3, title='test', device=self.pd2, block=2, created_by=self.u2)
        db3 = DataBlock.objects.create(org=self.o3, title='test', device=self.pd3, block=3, created_by=self.u2)
        db4 = DataBlock.objects.create(org=self.o3, title='some random title', device=self.pd3, block=4, created_by=self.u2)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['recordsTotal'], 0)

        resp = self.client.get(url+'?org={}'.format(self.o3.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['recordsTotal'], 3)

        resp = self.client.get(url+'?device={}'.format(self.pd1.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['recordsTotal'], 1)

        resp = self.client.get(url+'?org={}&device={}'.format(self.o3.slug, self.pd3.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['recordsTotal'], 2)

    def testBlockNumAtPost(self):
        url = reverse('datablock-list')
        payload = {
            'title': 'This is a new archive',
            'device': self.pd1.slug
        }

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user3@foo.com', password='pass')

        # Non-members should not be allowed to create block
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['block'], 1)
        self.assertEqual(deserialized['pid'], 'pid:000000')
        device = Device.objects.get(slug=self.pd1.slug)
        self.assertFalse(device.busy)

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['block'], 2)

        DataBlock.objects.get(device=self.pd1, block=1).delete()

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['block'], 3)
        self.assertEqual(deserialized['title'], 'This is a new archive')
        self.assertEqual(deserialized['description'], '')
        self.assertEqual(deserialized['org'], self.pd1.org.slug)
        device = Device.objects.get(slug=self.pd1.slug)
        self.assertFalse(device.busy)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')

        payload = {
            'title': 'An archive with on_complete',
            'description': 'this is a long description of the archive',
            'device': self.pd1.slug,
            'on_complete': {
                'device': {
                    'state': 'N0'
                }
            }
        }

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        deserialized = json.loads(resp.content.decode())
        id = deserialized['id']
        block = DataBlock.objects.get(id=id)
        self.assertEqual(block.block, 4)
        self.assertEqual(block.title, payload['title'])
        self.assertEqual(block.description, payload['description'])
        self.assertEqual(block.device.state, 'N0')
        self.assertFalse(block.device.active)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')

        payload = {
            'title': 'not-allowed',
            'description': 'Should not be allowed for operators',
            'device': self.pd1.slug
        }

        self.p1.org.register_user(self.u3, role='r1')
        self.assertFalse(self.p1.org.has_permission(self.u3, 'can_create_datablock'))

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testPostBusy(self):
        url = reverse('datablock-list')
        payload = {
            'title': 'This is a new archive',
            'device': self.pd1.slug
        }
        self.pd1.state = 'B1'
        self.pd1.save()

        ok = self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testPatch(self):
        db1 = DataBlock.objects.create(org=self.o2, title='Old Title', device=self.pd1, block=1, created_by=self.u2)
        url = reverse('datablock-detail', kwargs={'slug': db1.slug})
        payload = {
            'title': 'New title'
        }

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['title'], payload['title'])
        self.assertEqual(deserialized['block'], 1)

        payload = {
            'title': 'New title',
            'description': 'New description',
            'block': 0,
            'device': self.pd2.slug
        }

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['title'], payload['title'])
        self.assertEqual(deserialized['description'], payload['description'])
        # Ensure nothing else changed
        self.assertEqual(deserialized['block'], 1)
        self.assertEqual(deserialized['slug'], db1.slug)
        db2 = DataBlock.objects.get(slug=db1.slug)
        self.assertEqual(db2.device, self.pd1)

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')

        payload = {
            'title': 'not-allowed',
            'description': 'Should not be allowed for operators',
            'device': self.pd2.slug
        }

        self.p1.org.register_user(self.u3, role='r1')
        self.assertFalse(self.p1.org.has_permission(self.u3, 'can_create_datablock'))

        resp = self.client.patch(url, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testDelete(self):
        db1 = DataBlock.objects.create(org=self.o2, title='Old Title', device=self.pd1, block=1, created_by=self.u2)
        self.assertEqual(DataBlock.objects.count(), 1)
        url = reverse('datablock-detail', kwargs={'slug': db1.slug})

        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        self.client.login(email='user1@foo.com', password='pass')

        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(DataBlock.objects.count(), 0)

        self.client.logout()

    def testBlockProperties(self):
        db1 = DataBlock.objects.create(org=self.o1, title='test', device=self.pd1, block=1, created_by=self.u1)

        GenericProperty.objects.create_int_property(slug=self.pd1.slug,
                                                    created_by=self.u1,
                                                    name='prop1', value=4)
        GenericProperty.objects.create_str_property(slug=self.pd1.slug,
                                                    created_by=self.u1,
                                                    name='prop2', value='4')
        GenericProperty.objects.create_bool_property(slug=self.pd1.slug,
                                                     created_by=self.u1,
                                                     name='prop3', value=True)
        self.assertEqual(GenericProperty.objects.object_properties_qs(self.pd1).count(), 3)
        self.assertEqual(GenericProperty.objects.object_properties_qs(db1).count(), 0)

        action = ArchiveDeviceDataAction()
        action._block = db1
        action._device = self.pd1
        action._migrate_properties()
        self.assertEqual(GenericProperty.objects.object_properties_qs(self.pd1).count(), 0)
        self.assertEqual(GenericProperty.objects.object_properties_qs(db1).count(), 3)

        url = reverse('device-properties', kwargs={'slug': str(db1.slug)})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(len(deserialized), 3)
        self.assertEqual(deserialized[0]['name'], 'prop1')
        self.assertEqual(deserialized[1]['name'], 'prop2')
        self.assertEqual(deserialized[2]['name'], 'prop3')

        self.client.logout()

        # Staff has access to all
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(len(deserialized), 3)
        self.assertEqual(deserialized[0]['name'], 'prop1')
        self.assertEqual(deserialized[1]['name'], 'prop2')
        self.assertEqual(deserialized[2]['name'], 'prop3')

        self.client.logout()

        # Other Users don't have access
        self.assertFalse(self.o1.has_access(self.u3))
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testGetProperties(self):
        db1 = DataBlock.objects.create(org=self.o2, title='test', device=self.pd1, block=1, created_by=self.u2)
        db2 = DataBlock.objects.create(org=self.o3, title='test', device=self.pd2, block=2, created_by=self.u2)
        GenericProperty.objects.create_int_property(slug=db1.slug,
                                                    created_by=self.u1,
                                                    name='prop1', value=4)
        GenericProperty.objects.create_str_property(slug=db1.slug,
                                                    created_by=self.u1, is_system=True,
                                                    name='prop2', value='4')
        GenericProperty.objects.create_bool_property(slug=db2.slug,
                                                     created_by=self.u1,
                                                     name='prop3', value=True)

        url = reverse('datablock-properties', kwargs={'slug': str(db1.slug)})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(len(deserialized), 2)
        self.assertEqual(deserialized[0]['name'], 'prop1')
        self.assertEqual(deserialized[0]['type'], 'int')
        self.assertEqual(deserialized[0]['value'], 4)
        self.assertEqual(deserialized[0]['is_system'], False)
        self.assertEqual(deserialized[1]['name'], 'prop2')
        self.assertEqual(deserialized[1]['is_system'], True)
        self.assertEqual(deserialized[1]['type'], 'str')
        self.assertEqual(deserialized[1]['value'], '4')

        self.client.logout()

        # Staff has access to all
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(len(deserialized), 2)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        self.p1.org.register_user(self.u3, role='r1')
        self.assertFalse(self.p1.org.has_permission(self.u3, 'can_read_device_properties'))
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['detail'], 'You do not have permission to perform this action.')

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()
