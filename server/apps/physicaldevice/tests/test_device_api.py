import json
import pytz

from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_datetime

from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.project.models import Project
from apps.utils.test_util import TestMixin
from apps.sensorgraph.models import SensorGraph
from apps.streamer.models import Streamer, StreamerReport
from apps.stream.models import StreamId, StreamVariable
from apps.streamfilter.models import StreamFilter, StreamFilterAction, State, StateTransition, StreamFilterTrigger
from apps.streamfilter.serializers import StreamFilterSerializer
from apps.streamfilter.dynamodb import DynamoFilterLogModel, create_filter_log_table_if_needed, create_filter_log
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.streamnote.models import StreamNote
from apps.datablock.models import DataBlock
from apps.utils.timezone_utils import str_utc

from ..models import *

user_model = get_user_model()


class DeviceAPITestCase(TestMixin, APITestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()

    def tearDown(self):
        GenericProperty.objects.all().delete()
        DeviceStatus.objects.all().delete()
        StreamData.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()
        self.projectTestTearDown()

    def testDeleteDevice(self):
        """
        Ensure delete operations are protected
        """
        pd1 = Device.objects.create_device(id=1, project=self.p1, label='d1',
                                           template=self.dt1, created_by=self.u1, claimed_by=self.u2)
        url1 = reverse('device-detail', kwargs={'slug': str(pd1.slug)})

        resp = self.client.delete(url1)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        self.assertEqual(Device.objects.count(), 1)
        resp = self.client.delete(url1)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Device.objects.count(), 1)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.delete(url1)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Device.objects.count(), 1)

        resp = self.client.delete(url1+'?staff=1')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Device.objects.count(), 0)

        self.client.logout()

    def testGetDevice(self):
        """
        Ensure we can call GET on the device API.
        """
        url = reverse('device-list')

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)
        detail_url1 = reverse('device-detail', kwargs={'slug': str(pd1.slug)})
        detail_url2 = reverse('device-detail', kwargs={'slug': str(pd2.slug)})

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 0)

        resp = self.client.get(url+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        # Staff can retrieve any record
        resp = self.client.get(detail_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(detail_url2, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.get(detail_url1+'?staff=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], pd1.id)
        self.assertEqual(deserialized['label'], str(pd1.label))
        self.assertEqual(deserialized['slug'], str(pd1.slug))

        self.client.logout()

        # Staff has access to all
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        resp = self.client.get(detail_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], pd1.id)

        resp = self.client.get(detail_url2, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        resp = self.client.get(detail_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.get(detail_url2, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testGetBlock(self):
        """
        Ensure we can call GET on a DataBlock
        """
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        pd2 = Device.objects.create_device(project=self.p1, label='d2', template=self.dt1, created_by=self.u2)
        db1 = DataBlock.objects.create(org=self.o2, title='test1', device=pd1, block=1, created_by=self.u2)
        db2 = DataBlock.objects.create(org=self.o2, title='test2', device=pd2, block=1, created_by=self.u2)
        pd2.active = False
        pd2.save()

        block_url1 = reverse('device-detail', kwargs={'slug': str(db1.slug)})
        block_url2 = reverse('device-detail', kwargs={'slug': str(db2.slug)})

        # Staff can retrieve any record
        resp = self.client.get(block_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(block_url2, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

        # Staff has access to all
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(block_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], pd1.id)
        resp = self.client.get(block_url2, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['id'], pd2.id)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(block_url1, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.get(block_url2, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testGetDeviceWithFilter(self):
        """
        Ensure we can call GET with filters
        """
        url = reverse('device-list')+'?staff=1'

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        sg1 = SensorGraph.objects.create(name='SG 1',
                                         major_version=1,
                                         created_by=self.u1, org=self.o1)
        sg2 = SensorGraph.objects.create(name='SG 2',
                                         major_version=1,
                                         created_by=self.u1, org=self.o1)
        pd1 = Device.objects.create_device(project=self.p1, label='d1', sg=sg1, template=self.dt1, created_by=self.u1)
        pd2 = Device.objects.create_device(project=self.p2, label='d2', sg=sg1, template=self.dt1, created_by=self.u1)
        pd3 = Device.objects.create_device(project=None, label='Unclaimed', sg=sg1, template=self.dt1, created_by=self.u1)
        pd4 = Device.objects.create_device(project=self.p2, label='d2', sg=sg2, template=self.dt2,
                                           external_id='abc', created_by=self.u1)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)

        resp = self.client.get(url+'&project={}'.format(str(self.p1.id)), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        resp = self.client.get(url+'&project={}'.format(str(self.p2.id)), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)
        resp = self.client.get(url+'&project={}'.format(self.p2.slug), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)
        resp = self.client.get(url+'&org__slug={}'.format(str(self.p2.org.slug)), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        resp = self.client.get(url+'&sg={}'.format(str(sg1.slug)), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 3)

        resp = self.client.get(url+'&external_id=abc', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.assertEqual(deserialized['results'][0]['external_id'], 'abc')

        resp = self.client.get(url+'&sg={0}&project={1}'.format(str(sg1.slug), str(self.p1.id)), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        resp = self.client.get(url+'&dt={}'.format(str(self.dt2.slug)), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)

        resp = self.client.get(url+'&claimed=True', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 3)

        self.client.logout()

    def testGeInactiveDevices(self):
        url = reverse('device-list')

        sg1 = SensorGraph.objects.create(name='SG 1', major_version=1,
                                         created_by=self.u1, org=self.o1)
        sg2 = SensorGraph.objects.create(name='SG 2',
                                         major_version=1,
                                         created_by=self.u1, org=self.o1)

        pd1 = Device.objects.create_device(project=self.p1, label='d1', sg=sg1, template=self.dt1,
                                           created_by=self.u1)
        pd2 = Device.objects.create_device(project=self.p2, label='d2', sg=sg1, template=self.dt1,
                                           created_by=self.u1)
        pd3 = Device.objects.create_device(project=None, label='Unclaimed', sg=sg1, template=self.dt1,
                                           created_by=self.u1)
        pd4 = Device.objects.create_device(project=self.p2, label='d2', sg=sg2, template=self.dt2, active=False,
                                           external_id='abc', created_by=self.u1)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        staff_url = url  + '?staff=1'
        resp = self.client.get(staff_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)

        self.client.logout()

        self.p2.org.register_user(self.u2)
        self.assertTrue(self.p2.org.has_access(self.u2))
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        project_url = url+'?project={}'.format(self.p2.slug)
        resp = self.client.get(project_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        resp = self.client.get(project_url+'&all=0', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        resp = self.client.get(project_url+'&all=1', format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)

        self.client.logout()

    def testGetDeviceWithSlug(self):
        """
        Ensure we can call GET on the org API.
        """
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        pd1 = Device.objects.create_device(id=1, project=self.p1, label='d1', template=self.dt1, created_by=self.u2)

        for ok_slug in ['d--0001', 'd--0000-0001', 'd--0000-0000-0000-0001']:
            url = reverse('device-detail', kwargs={'slug': ok_slug})

            resp = self.client.get(url, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            deserialized = json.loads(resp.content.decode())
            self.assertEqual(deserialized['slug'], str(pd1.slug))

        for fail_slug in ['0001', str(pd1.id)]:
            url = reverse('device-detail', kwargs={'slug': fail_slug})

            resp = self.client.get(url, format='json')
            self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def testPatchDevice(self):
        """
        Ensure we can call GET on the org API.
        """
        pd1 = Device.objects.create_device(id=1, project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        url1 = reverse('device-detail', kwargs={'slug': str(pd1.slug)})

        payload = {
            'label':'d2',
            'lat': 40.741895,
            'lon': -73.989308
        }

        resp = self.client.put(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.patch(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        pd1 = Device.objects.get(id=1)
        self.assertEqual(pd1.label, payload['label'])
        self.assertEqual(float(pd1.lat), payload['lat'])
        self.assertEqual(float(pd1.lon), payload['lon'])

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.patch(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.p1.org.register_user(self.u3, role='r1')
        self.assertFalse(self.p1.org.has_permission(self.u3, 'can_modify_device'))
        resp = self.client.patch(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['detail'], 'User is not allowed to modify device')

        self.client.logout()

    def testPatchDeviceState(self):
        """
        Ensure we can call GET on the org API.
        """
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        pd1 = Device.objects.create_device(id=1, project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        url1 = reverse('device-detail', kwargs={'slug': str(pd1.slug)})

        payload = {
            'state':'N0'
        }

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.patch(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        pd1 = Device.objects.get(id=1)
        self.assertEqual(pd1.state, 'N0')
        self.assertFalse(pd1.active)

        self.client.logout()

    def testPatchDeviceTemplateAndSG(self):
        """
        Ensure that users cannot change template, but can change sg
        """
        sg2 = SensorGraph.objects.create(name='SG 2', major_version=1, app_tag=1030,
                                         created_by=self.u1, org=self.o1)

        pd1 = Device.objects.create_device(id=1, project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        url1 = reverse('device-detail', kwargs={'slug': str(pd1.slug)})

        template_payload = {
            'template': self.dt2.slug,
            'sg': sg2.slug
        }

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        # Not allowed for users
        resp = self.client.patch(url1, data=template_payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        pd1 = Device.objects.get(id=1)
        self.assertEqual(pd1.template.slug, self.dt1.slug)
        self.assertEqual(pd1.sg.slug, sg2.slug)

        resp = self.client.patch(url1+'?staff=1', data=template_payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        pd1 = Device.objects.get(id=1)
        self.assertEqual(pd1.template.slug, self.dt1.slug)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        pd1.template = self.dt1
        pd1.sg = sg2
        pd1.save()

        resp = self.client.patch(url1, data=template_payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        pd1 = Device.objects.get(id=1)
        self.assertEqual(pd1.template.slug, self.dt1.slug)
        self.assertEqual(pd1.sg.slug, sg2.slug)

        # ?staff=1 most be passed to force proper serializer
        resp = self.client.patch(url1+'?staff=1', data=template_payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        pd1 = Device.objects.get(id=1)
        self.assertEqual(pd1.template.slug, template_payload['template'])
        self.assertEqual(pd1.sg.slug, sg2.slug)

        self.client.logout()

    def testStaffPatchDevice(self):
        """
        Ensure we can call GET on the org API.
        """
        old_org = self.p1.org
        old_sg = SensorGraph.objects.create(name='SG 1', created_by=self.u1, org=self.o1)
        pd1 = Device.objects.create_device(id=1, project=self.p1, label='d1', sg=old_sg,
                                           template=self.dt1, created_by=self.u1, claimed_by=self.u2)
        url1 = reverse('device-detail', kwargs={'slug': str(pd1.slug)})

        payload = {
            'active': False,
            'label': 'Disabled Device'
        }

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.patch(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        pd1 = Device.objects.get(id=1)
        self.assertFalse(pd1.active)

        old_template = pd1.template
        new_template = DeviceTemplate.objects.create(external_sku='New Template', org=self.o1,
                                                     released_on=datetime.datetime.utcnow(),
                                                     created_by=self.u1)
        new_sg = SensorGraph.objects.create(name='SG 2', created_by=self.u1, org=self.o1)
        new_org = self.o3

        payload = {
            'org': new_org.slug,
            'template': new_template.slug,
            'sg': new_sg.slug,
            'claimed_by': self.u3.slug
        }

        resp = self.client.patch(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['template'], old_template.slug)
        self.assertEqual(deserialized['sg'], new_sg.slug)
        self.assertEqual(deserialized['org'], old_org.slug)
        self.assertEqual(deserialized['claimed_by'], self.u2.slug)

        resp = self.client.patch(url1+'?staff=1', data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['template'], old_template.slug)
        self.assertEqual(deserialized['org'], old_org.slug)
        self.assertEqual(deserialized['claimed_by'], self.u2.slug)

        self.client.logout()

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.patch(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['template'], old_template.slug)
        self.assertEqual(deserialized['org'], old_org.slug)
        self.assertEqual(deserialized['claimed_by'], self.u2.slug)

        resp = self.client.patch(url1+'?staff=1', data=payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['template'], new_template.slug)
        self.assertEqual(deserialized['org'], old_org.slug)
        self.assertEqual(deserialized['claimed_by'], self.u3.slug)

        self.client.logout()

    def testClaimable(self):
        pd1 = Device.objects.create_device(project=None, label='d1', template=self.dt1, created_by=self.u2)
        pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)
        pd3 = Device.objects.create_device(project=None, label='d3', template=self.dt1, created_by=self.u3, active=False)
        url1 = reverse('device-claimable')

        payload = {
            'slugs':[pd1.slug, pd2.slug, pd3.slug]
        }

        resp = self.client.post(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 3)
        results = deserialized['results']
        self.assertEqual(results[0]['slug'], pd1.slug)
        self.assertEqual(results[0]['claimable'], True)
        self.assertEqual(results[1]['slug'], pd2.slug)
        self.assertEqual(results[1]['claimable'], False)
        self.assertEqual(results[2]['slug'], pd3.slug)
        self.assertEqual(results[2]['claimable'], True)

        payload = {
            'slugs':[pd1.slug, 'abc']
        }
        resp = self.client.post(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        results = deserialized['results']
        self.assertEqual(results[0]['slug'], pd1.slug)
        self.assertEqual(results[0]['claimable'], True)

    def testClaimSuccess(self):
        pd1 = Device.objects.create_device(project=None, label='d1', template=self.dt1, created_by=self.u2)
        pd2 = Device.objects.create_device(project=None, label='d2', template=self.dt1, created_by=self.u2, active=False)
        pd3 = Device.objects.create_device(project=None, label='d3', template=self.dt1, created_by=self.u2)
        url1 = reverse('device-claim')

        # Try with project slug
        payload = {
            'device':pd1.slug,
            'project':self.p1.slug
        }

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['device'], pd1.slug)
        self.assertEqual(deserialized['project'], self.p1.slug)
        self.assertEqual(deserialized['project_id'], str(self.p1.id))
        self.assertEqual(deserialized['claimed'], True)

        # Try with project ID
        payload = {
            'device': pd2.slug,
            'project': str(self.p1.id)
        }

        resp = self.client.post(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['device'], pd2.slug)
        self.assertEqual(deserialized['project'], self.p1.slug)
        self.assertEqual(deserialized['project_id'], str(self.p1.id))
        self.assertEqual(deserialized['claimed'], True)

        # Try with bad device
        payload = {
            'device': 'foo',
            'project': str(self.p1.id)
        }

        resp = self.client.post(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        # Try with bad device
        payload = {
            'device': pd3.slug,
            'project': 'foo'
        }

        resp = self.client.post(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def testClaimFail(self):
        pd1 = Device.objects.create_device(project=None, label='d1', template=self.dt1, created_by=self.u2)
        pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)
        url1 = reverse('device-claim')

        payload = {
            'device':pd1.slug,
            'project':self.p1.slug
        }

        resp = self.client.post(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['detail'], 'No claim permissions')

        self.p1.org.register_user(self.u3, role='r1')
        resp = self.client.post(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['detail'], 'No claim permissions')

        payload = {
            'device':pd2.slug,
            'project':self.p1.slug
        }

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['detail'], 'Device is not claimable')

    def testPatchUnclaimDevice(self):
        pd1 = Device.objects.create_device(id=1, project=None, label='d1', template=self.dt1, created_by=self.u2)
        streamer = Streamer.objects.create(device=pd1, index=1, created_by=self.u1 )
        StreamerReport.objects.create(streamer=streamer, actual_first_id=11, actual_last_id=20, created_by=self.u1 )
        StreamerReport.objects.create(streamer=streamer, actual_first_id=21, actual_last_id=30, created_by=self.u1 )
        v1 = StreamVariable.objects.create_variable(
            name='Var X', project=self.p1, created_by=self.u3, lid=5,
        )
        v2 = StreamVariable.objects.create_variable(
            name='Var Y', project=self.p1, created_by=self.u3, lid=6,
        )
        claim_url = reverse('device-claim')
        unclaim_url = reverse('device-unclaim', kwargs={'slug': str(pd1.slug)})

        # Claim the device first
        claim_payload = {
            'device':pd1.slug,
            'project':self.p1.slug
        }
        unclaim_payload = {
            'clean_streams': True
        }

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(unclaim_payload, data=unclaim_payload)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.post(claim_url, data=claim_payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        pd1 = Device.objects.get(slug=pd1.slug)
        StreamId.objects.create_after_new_device(pd1)
        self.assertEqual(StreamId.objects.count(), 2)

        s1 = StreamId.objects.filter(variable=v1).first()
        s2 = StreamId.objects.filter(variable=v2).first()
        self.assertIsNotNone(s1)
        self.assertIsNotNone(s2)
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=6
        )
        StreamEventData.objects.create(
            timestamp=timezone.now(),
            device_timestamp=10,
            stream_slug=s2.slug,
            streamer_local_id=7
        )
        self.assertEqual(s1.get_data_count(), 2)
        self.assertEqual(s2.get_event_count(), 1)
        self.assertEqual(StreamData.objects.count(), 2)
        self.assertEqual(StreamEventData.objects.count(), 1)

        # Create Device properties
        GenericProperty.objects.create_int_property(slug=pd1.slug,
                                                    created_by=self.u1,
                                                    name='prop1', value=4)
        GenericProperty.objects.create_str_property(slug=pd1.slug,
                                                    created_by=self.u1,
                                                    name='prop2', value='4')
        GenericProperty.objects.create_bool_property(slug=pd1.slug,
                                                     created_by=self.u1,
                                                     name='prop3', value=True)

        self.assertEqual(GenericProperty.objects.object_properties_qs(pd1).count(), 3)

        # Now try to unclaim
        # create filter logs
        with self.settings(USE_DYNAMODB_FILTERLOG_DB=True):
            if DynamoFilterLogModel.exists():
                DynamoFilterLogModel.delete_table()
            create_filter_log_table_if_needed()
            for stream in pd1.streamids.all():
                create_filter_log(stream.slug, datetime.datetime.utcnow(), "src", "dst", "trigger")
            self.assertEqual(DynamoFilterLogModel.count(), pd1.streamids.count())

            ok = self.client.login(email='user3@foo.com', password='pass')
            self.assertTrue(ok)

            resp = self.client.post(unclaim_url, data=unclaim_payload)
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
            deserialized = json.loads(resp.content.decode())
            self.assertEqual(deserialized['detail'], 'You do not have permission to perform this action.')

            self.p1.org.register_user(self.u3, role='r1')
            resp = self.client.post(unclaim_url, data=unclaim_payload)
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
            deserialized = json.loads(resp.content.decode())
            self.assertEqual(deserialized['detail'], 'No unclaim permissions')

            self.client.logout()

            ok = self.client.login(email='user2@foo.com', password='pass')
            self.assertTrue(ok)

            self.assertEqual(StreamId.objects.count(), 2)
            self.assertEqual(pd1.streamids.count(), 2)
            self.assertEqual(Streamer.objects.count(), 1)
            self.assertEqual(StreamerReport.objects.count(), 2)
            resp = self.client.post(unclaim_url, data=unclaim_payload)
            self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
            pd1 = Device.objects.get(id=1)
            self.assertEqual(pd1.label, 'Device (0001)')
            self.assertEqual(pd1.lat, None)
            self.assertEqual(pd1.lon, None)
            self.assertEqual(pd1.project, None)
            self.assertEqual(pd1.org, None)
            self.assertEqual(Streamer.objects.count(), 0)
            self.assertEqual(StreamerReport.objects.count(), 0)
            self.assertEqual(StreamId.objects.count(), 0)
            self.assertEqual(pd1.streamids.count(), 0)
            self.assertEqual(StreamData.objects.count(), 0)
            self.assertEqual(StreamEventData.objects.count(), 0)
            self.assertEqual(GenericProperty.objects.object_properties_qs(pd1).count(), 0)
            self.assertEqual(DynamoFilterLogModel.count(), 0)

            self.client.logout()

    def testGetProperties(self):
        GenericProperty.objects.create_int_property(slug='d--0000-0000-0000-0100',
                                                    created_by=self.u1,
                                                    name='prop1', value=4)
        GenericProperty.objects.create_str_property(slug='d--0000-0000-0000-0100',
                                                    created_by=self.u1, is_system=True,
                                                    name='prop2', value='4')
        GenericProperty.objects.create_bool_property(slug='d--0000-0000-0000-0002',
                                                     created_by=self.u1,
                                                     name='prop3', value=True)
        d1 = Device.objects.create(id=0x100, project=self.p1, org=self.p1.org, template=self.dt1, created_by=self.u2)
        url = reverse('device-properties', kwargs={'slug': str(d1.slug)})

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
        self.assertEqual(deserialized['detail'], 'User has no access to read properties')

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testPostProperties(self):
        d1 = Device.objects.create(id=0x100, project=self.p1, org=self.p1.org, template=self.dt1, created_by=self.u2)
        url = reverse('device-new-property', kwargs={'slug': str(d1.slug)})

        payload = {
            'name': 'NewProp1'
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        payload['int_value'] = 5
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        payload = {
            'name': 'NewProp2',
            'str_value': '6'
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        payload = {
            'name': 'NewProp3',
            'is_system': True,
            'bool_value': True
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        qs = d1.get_properties_qs()
        self.assertEqual(qs.count(), 3)
        self.assertEqual(qs[0].value, 5)
        self.assertFalse(qs[0].is_system)
        self.assertEqual(qs[1].value, '6')
        self.assertFalse(qs[1].is_system)
        self.assertEqual(qs[2].value, True)
        self.assertTrue(qs[2].is_system)

        payload = {
            'name': 'NewProp4',
            'int_value': 7,
            'bool_value': True
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        payload = {
            'name': 'NewProp5',
            'int_value': 7,
            'str_value': 'Foo',
            'bool_value': True
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.logout()

        # Staff has access to all
        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            'name': 'NewProp4',
            'bool_value': True
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        qs = d1.get_properties_qs()
        self.assertEqual(qs.count(), 4)
        p4 = qs.get(name='NewProp4')
        self.assertTrue(p4.value)

        payload = {
            'name': 'NewProp4',
            'bool_value': False
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        qs = d1.get_properties_qs()
        self.assertEqual(qs.count(), 4)
        p4 = qs.get(name='NewProp4')
        self.assertFalse(p4.value)

        self.client.logout()

        # Other Users don't have access
        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        payload = {
            'name': 'NewProp5',
            'bool_value': True
        }
        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testPostPropertiesNoString(self):
        d1 = Device.objects.create(id=0x100, project=self.p1, template=self.dt1, created_by=self.u2)
        url = reverse('device-new-property', kwargs={'slug': str(d1.slug)})

        # Test that we can write null values
        payload = {
            'name': 'NewProp1',
            'str_value': ' '
        }

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url, data=payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        qs = d1.get_properties_qs()
        self.assertEqual(qs.count(), 1)
        p5 = qs.get(name='NewProp1')
        self.assertEqual(p5.value, '')

        self.client.logout()

    def testDeviceHealthSettingAPI(self):
        pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        pd2 = Device.objects.create_device(project=None, label='d2', template=self.dt1, created_by=self.u3)
        pd1.get_or_create_status()
        pd2.get_or_create_status()
        self.assertEqual(DeviceStatus.objects.count(), 2)

        url = reverse("device-health", kwargs={"slug": pd1.slug})

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        # Create new dynamo device model if not exists
        payload = {
            'health_check_enabled': False,
            'health_check_period': 900,
            'notification_recipients': ['org:all']
        }
        resp = self.client.patch(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        st1 = pd1.get_or_create_status()
        self.assertFalse(st1.health_check_enabled)
        self.assertEqual(st1.health_check_period, 900)

        # update
        payload = {
            'health_check_enabled': True,
            'health_check_period': 1800,
            'notification_recipient': ['org:admin']
        }
        resp = self.client.patch(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        st1 = pd1.get_or_create_status()
        self.assertTrue(st1.health_check_enabled)
        self.assertEqual(st1.health_check_period, 1800)

        self.client.logout()

    def testGetDeviceStatus(self):
        pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        st1 = pd1.get_or_create_status()
        self.assertEqual(DeviceStatus.objects.count(), 1)

        streamer = Streamer.objects.create(device=pd1,
                                           index=1,
                                           created_by=self.u2)

        url = reverse("device-health", kwargs={"slug": pd1.slug})

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        # When device has no report and non exist in dynamodb table
        resp = self.client.get(url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertIsNone(deserialized['last_report_ts'], None)
        self.assertEqual(deserialized['alert'], 'DSBL')

        st1.health_check_enabled = True
        st1.health_check_period = 3600
        st1.notification_recipients = ['org:admin']
        st1.last_report_ts = timezone.now() - datetime.timedelta(seconds=3601)
        st1.save()

        resp = self.client.get(url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertIsNotNone(deserialized['last_report_ts'])
        self.assertEqual(deserialized['alert'], 'FAIL')

        self.client.logout()

    def testGetDeviceFilterLog(self):
        with self.settings(USE_DYNAMODB_FILTERLOG_DB=True):
            if DynamoFilterLogModel.exists():
                DynamoFilterLogModel.delete_table()
            create_filter_log_table_if_needed()

            pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
            v1 = StreamVariable.objects.create_variable(
                name='Var A', project=self.p1, created_by=self.u2, lid=0x5001,
            )
            s1 = StreamId.objects.create_stream(
                project=self.p1, variable=v1, device=pd1, created_by=self.u2
            )
            f = StreamFilter.objects.create_filter_from_streamid(name='Filter test',
                                                                 input_stream=s1,
                                                                 created_by=self.u2)
            state1 = State.objects.create(label="state1", filter=f, created_by=self.u2)
            state2 = State.objects.create(label="state2", filter=f, created_by=self.u2)
            a = StreamFilterAction.objects.create(
                type="eml",created_by=self.u2, on='exit', state=state1
            )
            transition = StateTransition.objects.create(src=state1, dst=state2, filter=f, created_by=self.u2)
            t = StreamFilterTrigger.objects.create(operator='gt', threshold=10, created_by=self.u2, filter=f, transition=transition)
            t0 = parse_datetime('2017-01-10T10:00:00Z')
            url = reverse("device-filterlog", kwargs={"slug": pd1.slug})
            serializer = StreamFilterSerializer(f)
            f_data = serializer.data
            self.assertEqual(DynamoFilterLogModel.count(), 0)

            log_id = create_filter_log(s1.slug, t0, state1.label, state2.label, f_data['transitions'][0]['triggers'])

            ok = self.client.login(email='user2@foo.com', password='pass')
            self.assertTrue(ok)
            self.assertEqual(DynamoFilterLogModel.count(str(log_id)), 1)

            resp = self.client.get(url, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            deserialized = json.loads(resp.content.decode())
            self.assertEqual(len(deserialized['device_filter_logs']), 1)
            log = deserialized['device_filter_logs'][0]

            self.assertEqual(log['uuid'], str(log_id))
            self.assertEqual(log['target_slug'], s1.slug)
            self.assertEqual(log['timestamp'], '2017-01-10T10:00:00Z')
            self.assertEqual(log['src'], "state1")
            self.assertEqual(log['dst'], "state2")
            self.assertEqual(len(log['triggers']), 1)
            self.assertEqual(log['triggers'][0]['operator'], "gt")
            self.assertEqual(log['triggers'][0]['threshold'], 10)

            DynamoFilterLogModel.delete_table()
            self.client.logout()

    def testDeviceUpgrade(self):
        pd1 = Device.objects.create_device(project=None, label='d1', template=self.dt1, created_by=self.u2)
        url1 = reverse('device-upgrade', kwargs={"slug": pd1.slug})

        payload = {
            'firmware': 'v2.9.1'
        }

        resp = self.client.post(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        self.assertEqual(StreamNote.objects.filter(target_slug=pd1.slug).count(), 0)
        resp = self.client.post(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['slug'], pd1.slug)
        self.assertEqual(StreamNote.objects.filter(target_slug=pd1.slug).count(), 1)
        note = StreamNote.objects.filter(target_slug=pd1.slug).first()
        self.assertEqual(note.note, 'Device {} firmware upgraded to {}'.format(
            pd1.slug, payload['firmware'])
        )

        self.client.logout()

        ok = self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.post(url1, data=payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testDevicePermission(self):
        """
        Ensure we can call GET on the org API.
        """
        pd1 = Device.objects.create_device(id=1, project=self.p1, label='d1', template=self.dt1, created_by=self.u2)

        ok = self.client.login(email='user3@foo.com', password='pass')
        self.assertTrue(ok)

        url_reset = reverse('device-reset', kwargs={'slug': str(pd1.slug)})
        ts_now0 = parse_datetime('2018-01-02T23:31:36Z')
        payload_trim = {
            'start': str_utc(ts_now0 + datetime.timedelta(seconds=101)),
            'end': str_utc(ts_now0 + datetime.timedelta(seconds=201)),
        }
        url_trim = reverse('device-trim', kwargs={'slug': pd1.slug})

        resp = self.client.post(url_reset, data={})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.post(url_trim, data=payload_trim)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        membership = self.p1.org.register_user(self.u3, role='m1')
        membership.permissions['can_modify_device'] = False
        membership.permissions['can_reset_device'] = False
        membership.save()

        url_reset = reverse('device-reset', kwargs={'slug': str(pd1.slug)})
        resp = self.client.post(url_reset, data={})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.post(url_trim, data=payload_trim)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        membership.permissions['can_modify_device'] = True
        membership.permissions['can_reset_device'] = True
        membership.save()

        url_reset = reverse('device-reset', kwargs={'slug': str(pd1.slug)})
        resp = self.client.post(url_reset, data={})
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(resp.content.decode())
        self.assertTrue('pid' in deserialized)
        self.assertEqual(deserialized['pid'], 'pid:000000')
        resp = self.client.post(url_trim, data=payload_trim)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        self.client.logout()

    def testDeviceFullReset(self):
        """
        Ensure we can do a full reset
        """
        pd1 = Device.objects.create_device(id=1, project=self.p1, label='d1', template=self.dt1, created_by=self.u2)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        url_reset = reverse('device-reset', kwargs={'slug': str(pd1.slug)})
        resp = self.client.post(url_reset, data={ 'full': True})
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(resp.content.decode())
        self.assertTrue('pid' in deserialized)
        self.assertEqual(deserialized['pid'], 'pid:000000')

        self.client.logout()

    def testDeviceResetNoProperties(self):
        """
        Ensure we can do a reset without deleting proerties
        """
        pd1 = Device.objects.create_device(id=1, project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        GenericProperty.objects.create_int_property(slug=pd1.slug,
                                                    created_by=self.u1,
                                                    name='prop1', value=4)
        self.assertTrue(GenericProperty.objects.count() == 1)

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        url_reset = reverse('device-reset', kwargs={'slug': str(pd1.slug)})
        resp = self.client.post(url_reset, data={ 'include_properties': False})
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(resp.content.decode())
        self.assertTrue('pid' in deserialized)
        self.assertEqual(deserialized['pid'], 'pid:000000')
        self.assertTrue(GenericProperty.objects.count() == 1)

        self.client.logout()

    def testDeviceResetNoNotes(self):
        """
        Ensure we can do a reset without deleting proerties
        """
        pd1 = Device.objects.create_device(id=1, project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        GenericProperty.objects.create_int_property(slug=pd1.slug,
                                                    created_by=self.u1,
                                                    name='prop1', value=4)
        self.assertTrue(GenericProperty.objects.count() == 1)

        StreamNote.objects.create(
            target_slug=pd1.slug,
            timestamp=timezone.now(),
            created_by=self.u1,
            note='Note 1'
        )

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        url_reset = reverse('device-reset', kwargs={'slug': str(pd1.slug)})
        resp = self.client.post(url_reset, data={ 'include_notes_and_locations': False})
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        deserialized = json.loads(resp.content.decode())
        self.assertTrue('pid' in deserialized)
        self.assertEqual(deserialized['pid'], 'pid:000000')
        self.assertTrue(GenericProperty.objects.count() == 0)
        self.assertTrue(StreamNote.objects.count() == 2)

        self.client.logout()
    
    def testPostBusy(self):
        d1 = Device.objects.create(id=0x100, project=self.p1, org=self.p1.org, state='B1',
                                   template=self.dt1, created_by=self.u2)

        url_reset = reverse('device-reset', kwargs={'slug': str(d1.slug)})
        ts_now0 = parse_datetime('2018-01-02T23:31:36Z')
        payload_trim = {
            'start': str_utc(ts_now0 + datetime.timedelta(seconds=101)),
            'end': str_utc(ts_now0 + datetime.timedelta(seconds=201)),
        }
        url_trim = reverse('device-trim', kwargs={'slug': d1.slug})

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.post(url_reset, data={})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.post(url_trim, data=payload_trim)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def testGetDeviceExtraInfo(self):
        """
        Ensure we can call GET on the device API.
        """
        pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        url = reverse('device-extra', kwargs={'slug': pd1.slug})

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['stream_counts'], {})

        v1 = StreamVariable.objects.create_variable(
            name='Var X', project=self.p1, created_by=self.u3, lid=5,
        )
        v2 = StreamVariable.objects.create_variable(
            name='Var Y', project=self.p1, created_by=self.u3, lid=6,
        )
        StreamId.objects.create_after_new_device(pd1)
        self.assertEqual(StreamId.objects.count(), 2)

        s1 = StreamId.objects.filter(variable=v1).first()
        s2 = StreamId.objects.filter(variable=v2).first()
        self.assertIsNotNone(s1)
        self.assertIsNotNone(s2)

        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=5
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=6
        )
        StreamData.objects.create(
            stream_slug=s2.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=7
        )
        StreamData.objects.create(
            stream_slug=s1.slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=9
        )
        system_stream_slug='s--{}--{}--5800'.format(pd1.project.formatted_gid, pd1.formatted_gid)
        StreamData.objects.create(
            stream_slug=system_stream_slug,
            type='Num',
            timestamp=timezone.now(),
            int_value=8
        )

        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(len(deserialized['stream_counts'].keys()), 3)
        self.assertTrue(s1.slug in deserialized['stream_counts'])
        self.assertTrue(s2.slug in deserialized['stream_counts'])
        self.assertTrue(system_stream_slug in deserialized['stream_counts'])
        self.assertEqual(deserialized['stream_counts'][s1.slug]['data_cnt'], 3)
        self.assertEqual(deserialized['stream_counts'][s2.slug]['data_cnt'], 1)
        self.assertEqual(deserialized['stream_counts'][system_stream_slug]['data_cnt'], 1)
        self.assertTrue(deserialized['stream_counts'][s1.slug]['has_streamid'])
        self.assertTrue(deserialized['stream_counts'][s2.slug]['has_streamid'])
        self.assertFalse(deserialized['stream_counts'][system_stream_slug]['has_streamid'])

        self.client.logout()

