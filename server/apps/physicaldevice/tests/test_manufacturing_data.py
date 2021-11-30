import datetime
import json

from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.deviceauth.models import DeviceKey
from apps.devicetemplate.models import DeviceTemplate
from apps.org.models import AuthAPIKey, Org
from apps.physicaldevice.models import Device
from apps.physicaldevice.serializers import ManufacturingDataVirtualDeviceSerializer
from apps.project.models import Project
from apps.sensorgraph.models import SensorGraph
from apps.utils.api_key_utils import get_apikey_object_from_generated_key
from apps.utils.test_util import TestMixin

user_model = get_user_model()


class ManufacturingDataAPITestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.api_key_o2, self.generated_key_o2 = AuthAPIKey.objects.create_key(name="API key o2",
                                                                               org=self.o2)
        self.api_key_o3, self.generated_key_o3 = AuthAPIKey.objects.create_key(name="API key o3",
                                                                               org=self.o3)

        self.sg1 = SensorGraph.objects.create(name='SG 1',
                                              major_version=1,
                                              created_by=self.u1, org=self.o2)
        self.sg2 = SensorGraph.objects.create(name='SG 2',
                                              major_version=1,
                                              created_by=self.u1, org=self.o3)


    def tearDown(self):
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()
        AuthAPIKey.objects.all().delete()

    def assertDeviceIsSame(self, result, expected: Device, claimed):
        # Inputs: result = dictionary, expected = Device, claimed = boolean
        self.assertEqual(result['slug'], expected.slug)
        self.assertEqual(result['sg'], expected.sg.slug)
        self.assertEqual(result['template'], expected.template.slug)
        self.assertEqual(result['claimed'], claimed)

    def testPost(self):
        """
        For security reasons, ensure that the post does not work, even as a super user
        """
        url = reverse('manufacturingdata-list')
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key_o2)
        }
        payload = {
            'external_sku': 'foo',
            'org': str(self.o1.slug),
            'major_version': 2, 'patch_version': 1,
            'os_tag': 2050,
            'os_major_version': 1,
            'hw_tag': 1024,
            'hw_major_version': 1,
            'released_on': '2016-09-23'
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.post(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testGetWithAPIKey(self):
        """
        Ensure that we can use an API key to get manufacturing data
        """
        url = reverse('manufacturingdata-list')
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key_o2)
        }

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        pd1 = Device.objects.create_device(project=self.p1, label='d1', sg=self.sg1, template=self.dt1, created_by=self.u1)
        pd2 = Device.objects.create_device(project=self.p2, label='d2', sg=self.sg2, template=self.dt1, created_by=self.u1)

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)
        device = deserialized['results'][0]
        self.assertDeviceIsSame(device, pd1, True)

    def testAPIKeyOtherApis(self):
        """
        Ensure that API call fails on all non-GET methods of a key/token-enabled API
        """

        url = reverse('manufacturingdata-list')
        payload = {
            'external_sku': 'foo',
            'org': str(self.o1.slug),
            'major_version': 2, 'patch_version': 1,
            'os_tag': 2050,
            'os_major_version': 1,
            'hw_tag': 1024,
            'hw_major_version': 1,
            'released_on': '2016-09-23'
        }
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key_o2)
        }
        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 0)

        response = self.client.post(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.put(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.patch(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.delete(url, payload, format='json', **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(deserialized['count'], 0)

        # Try with truncated apikey = should fail
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key_o2[0:2])
        }
        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testGetDeviceWithFilter(self):
        """
        Ensure we can call GET with filters
        Also, checks that we do not get data across organizations
        """

        url = reverse('manufacturingdata-list')
        auth_headers_o2 = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key_o2)
        }

        auth_headers_o3 = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key_o3)
        }

        pd1 = Device.objects.create_device(project=self.p1, label='d1', sg=self.sg1, template=self.dt1, created_by=self.u1)
        pd2 = Device.objects.create_device(project=self.p2, label='d2', sg=self.sg1, template=self.dt1, created_by=self.u1)
        pd3 = Device.objects.create_device(project=self.p2, label='d3', sg=self.sg1, template=self.dt2, created_by=self.u1)
        pd4 = Device.objects.create_device(project=self.p2, label='d4', sg=self.sg2, template=self.dt2,
                                           external_id='abc', created_by=self.u1)
        pd5 = Device.objects.create_device(project=self.p1, label='d5', sg=self.sg2, template=self.dt2,
                                           external_id='def', created_by=self.u1)

        # Create some unrelated devices (for filtering out)
        o4 = Org.objects.create_org(name='Org 3 - Unrelated data', created_by=self.u3)
        p3 = Project.objects.create(name='Project 3', project_template=self.pt1,
                                         created_by=self.u3, org=o4)
        sg3 = SensorGraph.objects.create(name='SG 3',
                                         major_version=1,
                                         created_by=self.u1, org=o4)
        dt4 = DeviceTemplate.objects.create(external_sku='Device 4', org=o4, os_tag=1024,
                                                 os_major_version=0, os_minor_version=1,
                                                 released_on=datetime.datetime.utcnow(),
                                                 created_by=self.u1)
        pd6 = Device.objects.create_device(project=p3, label='d6', sg=sg3, template=dt4, created_by=self.u1)
        pd7 = Device.objects.create_device(project=p3, label='d7', sg=sg3, template=dt4, created_by=self.u1)

        # Call the API with different filters
        resp = self.client.get(url, **auth_headers_o2, format='json')
        result_dict = {
            pd1.slug: pd1,
            pd5.slug: pd5
        }
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)
        for device in deserialized['results']:
            self.assertDeviceIsSame(device, result_dict[device['slug']], True)

        resp = self.client.get(url+'?org__slug={}'.format(str(self.p2.org.slug)), **auth_headers_o3, format='json')
        result_dict = {
            pd2.slug: pd2,
            pd3.slug: pd3,
            pd4.slug: pd4,
        }
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 3)
        for device in deserialized['results']:
            self.assertDeviceIsSame(device, result_dict[device['slug']], True)

        resp = self.client.get(url+'?sg={}'.format(str(self.sg1.slug)), **auth_headers_o3, format='json')
        result_dict = {
            pd2.slug: pd2,
            pd3.slug: pd3,
        }
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)
        for device in deserialized['results']:
            self.assertDeviceIsSame(device, result_dict[device['slug']], True)
            self.assertEqual(device['sg'], self.sg1.slug)

        resp = self.client.get(url+'?dt={}'.format(str(self.dt2.slug)), **auth_headers_o3, format='json')
        result_dict = {
            pd3.slug: pd3,
            pd4.slug: pd4,
        }
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)
        for device in deserialized['results']:
            self.assertDeviceIsSame(device, result_dict[device['slug']], True)
            self.assertEqual(device['template'], self.dt2.slug)

        resp = self.client.get(url+'?sg={0}&dt={1}'.format(str(self.sg2.slug), str(self.dt2.slug)), **auth_headers_o3, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        device = deserialized['results'][0]
        self.assertDeviceIsSame(device, result_dict[device['slug']], True)
        self.assertEqual(device['sg'], self.sg2.slug)
        self.assertEqual(device['template'], self.dt2.slug)

    def testClaimedFilter(self):
        """
        Ensure that unclaimed devices are not seen
        """

        url = reverse('manufacturingdata-list')
        auth_headers_o2 = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key_o2)
        }
        auth_headers_o3 = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key_o3)
        }

        pd1 = Device.objects.create_device(project=self.p1, label='d1', sg=self.sg1, template=self.dt1, created_by=self.u1)
        pd2 = Device.objects.create_device(project=self.p2, label='d2', sg=self.sg1, template=self.dt1, created_by=self.u1)
        pd3 = Device.objects.create_device(project=None, label='Unclaimed', sg=self.sg1, template=self.dt1, created_by=self.u1)
        pd4 = Device.objects.create_device(project=self.p2, label='d2', sg=self.sg2, template=self.dt2,
                                           external_id='abc', created_by=self.u1)

        resp = self.client.get(url, **auth_headers_o3, format='json')
        result_slug = [pd2.slug, pd4.slug]
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 2)
        for device in deserialized['results']:
            self.assertIn(device['slug'], result_slug)
            self.assertEqual(device['claimed'], True)

    def testDeviceSlugFilter(self):
        """
        Ensure we cannot get other org devices through GET call with device slug
        """

        url = reverse('manufacturingdata-list')
        auth_headers_o2 = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key_o2)
        }

        auth_headers_o3 = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key_o3)
        }

        pd1 = Device.objects.create_device(project=self.p1, label='d1', sg=self.sg1, template=self.dt1, created_by=self.u1)
        pd2 = Device.objects.create_device(project=self.p2, label='d2', sg=self.sg1, template=self.dt1, created_by=self.u1)
        pd3 = Device.objects.create_device(project=self.p2, label='d3', sg=self.sg1, template=self.dt2, created_by=self.u1)
        pd4 = Device.objects.create_device(project=self.p2, label='d4', sg=self.sg2, template=self.dt2,
                                           external_id='abc', created_by=self.u1)
        pd5 = Device.objects.create_device(project=self.p2, label='d5', sg=self.sg2, template=self.dt2,
                                           external_id='def', created_by=self.u1)

        # Create some unrelated devices (for filtering out)
        o4 = Org.objects.create_org(name='Org 3 - Unrelated data', created_by=self.u3)
        p3 = Project.objects.create(name='Project 3', project_template=self.pt1,
                                         created_by=self.u3, org=o4)
        sg3 = SensorGraph.objects.create(name='SG 3',
                                         major_version=1,
                                         created_by=self.u1, org=o4)
        dt4 = DeviceTemplate.objects.create(external_sku='Device 4', org=o4, os_tag=1024,
                                                 os_major_version=0, os_minor_version=1,
                                                 released_on=datetime.datetime.utcnow(),
                                                 created_by=self.u1)
        pd6 = Device.objects.create_device(project=p3, label='d6', sg=sg3, template=dt4, created_by=self.u1)
        pd7 = Device.objects.create_device(project=p3, label='d7', sg=sg3, template=dt4, created_by=self.u1)

        # Call the API with different filters
        # TODO verify each device on each get call
        resp = self.client.get(url, **auth_headers_o2, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        device = deserialized['results'][0]
        self.assertDeviceIsSame(device, pd1, True)

        # Get the baseline number of devices (for org 3)
        resp = self.client.get(url+'?org__slug={}'.format(str(self.p2.org.slug)), **auth_headers_o3, format='json')
        baseline_count = deserialized['count']

        resp = self.client.get(url+'?slug={}'.format(str(pd2.slug)), **auth_headers_o3, format='json')
        result_slug = [pd2.slug, pd3.slug, pd4.slug, pd5.slug]
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)
        for device in deserialized['results']:
            self.assertIn(device['slug'], result_slug)

        resp = self.client.get(url+'?pk={}'.format(str(pd2.slug)), **auth_headers_o3, format='json')
        result_slug = [pd2.slug, pd3.slug, pd4.slug, pd5.slug]
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)
        for device in deserialized['results']:
            self.assertIn(device['slug'], result_slug)

        resp = self.client.get(url+'?pk={}'.format(str(pd2.id)), **auth_headers_o3, format='json')
        result_slug = [pd2.slug, pd3.slug, pd4.slug, pd5.slug]
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)
        for device in deserialized['results']:
            self.assertIn(device['slug'], result_slug)

        resp = self.client.get(url+'?slug={}'.format(str(pd1.slug)), **auth_headers_o3, format='json')
        result_slug = [pd2.slug, pd3.slug, pd4.slug, pd5.slug]
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)
        for device in deserialized['results']:
            self.assertIn(device['slug'], result_slug)

        resp = self.client.get(url+'?pk={}'.format(str(pd1.slug)), **auth_headers_o3, format='json')
        result_slug = [pd2.slug, pd3.slug, pd4.slug, pd5.slug]
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)
        for device in deserialized['results']:
            self.assertIn(device['slug'], result_slug)

        resp = self.client.get(url+'?pk={}'.format(str(pd1.id)), **auth_headers_o3, format='json')
        result_slug = [pd2.slug, pd3.slug, pd4.slug, pd5.slug]
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 4)
        for device in deserialized['results']:
            self.assertIn(device['slug'], result_slug)

    def testDeviceSlugUrl(self):
        """
        Ensure we cannot get other org devices through GET call with device slug
        """

        url = reverse('manufacturingdata-list')
        auth_headers_o2 = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key_o2)
        }

        auth_headers_o3 = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key_o3)
        }

        pd1 = Device.objects.create_device(project=self.p1, label='d1', sg=self.sg1, template=self.dt1, created_by=self.u1)
        pd2 = Device.objects.create_device(project=self.p2, label='d2', sg=self.sg1, template=self.dt1, created_by=self.u1)

        resp = self.client.get(url+'{}/'.format(str(pd1.slug)), **auth_headers_o2, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        device = json.loads(resp.content.decode())
        self.assertIsNotNone(device)
        self.assertDeviceIsSame(device, pd1, True)

        resp = self.client.get(url+'{}/'.format(str(pd1.slug)), **auth_headers_o3, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def testRevokedAPIKey(self):
        """
        Ensure that we cannot use a revoked API key
        """
        url = reverse('manufacturingdata-list')
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key_o2)
        }
        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        apikey = get_apikey_object_from_generated_key(self.generated_key_o2)
        apikey.revoked = True
        apikey.save()

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testExpiredAPIKey(self):
        """
        Ensure that we cannot use an expired API key
        """
        url = reverse('manufacturingdata-list')
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key_o2)
        }
        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        apikey = get_apikey_object_from_generated_key(self.generated_key_o2)
        apikey.expiry_date = timezone.now() - datetime.timedelta(days=1)
        apikey.save()

        response = self.client.get(url, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_virtual_serializer(self):
        sg_avail = SensorGraph.objects.create(
            name='forwarder-generic', major_version=1,
            created_by=self.u1, org=self.o2
        )
        self.assertEqual(sg_avail.slug, "forwarder-generic-v1-0-0")
        sg_unavail = SensorGraph.objects.create(
            name='Development', major_version=1,
            created_by=self.u1, org=self.o2
        )
        self.assertEqual(sg_unavail.slug, "development-v1-0-0")
        ser = ManufacturingDataVirtualDeviceSerializer(data={
            "sg": sg_avail.slug,
            "user": self.u1.slug,
            "org": self.o1.slug
        })
        self.assertTrue(ser.is_valid())

        ser = ManufacturingDataVirtualDeviceSerializer(data={
            "sg": sg_unavail.slug,
            "user": self.u2.slug,
            "org": self.o1.slug
        })
        self.assertFalse(ser.is_valid())
        self.assertIn("user", ser.errors)
        self.assertIn("sg", ser.errors)

    def test_create_virtual_device(self):
        url = reverse('manufacturingdata-create-virtual')
        sg_avail = SensorGraph.objects.create(
            name='forwarder-generic', major_version=1,
            created_by=self.u1, org=self.o2
        )
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key_o2)
        }
        DeviceTemplate.objects.create_template(
            org=self.o2,
            created_by=self.u1,
            external_sku="Generic Virtual Device",
            family="Virtual",
            released_on=datetime.date.today(),
            major_version=1
        )

        data = {
            "sg": sg_avail.slug,
            "user": self.u1.slug
        }
        response = self.client.post(url, data, **auth_headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(Device.objects.count(), 1)
        device = Device.objects.first()
        self.assertEqual(device.org, self.o2)
        self.assertEqual(device.created_by, self.u1)
        self.assertEqual(device.claimed_by, self.u1)
        self.assertEqual(device.sg, sg_avail)
        self.assertIsNone(device.project)
        self.assertEqual(device.label, "")
        self.assertEqual(device.template.slug, "generic-virtual-device-v1-0-0")

        data = {
            "sg": "",
            "user": self.u1.slug
        }
        response = self.client.post(url, data, **auth_headers)
        self.assertContains(
            response, 'This field may not be null.',
            status_code=status.HTTP_400_BAD_REQUEST
        )
        self.assertEqual(Device.objects.count(), 1)

        data = {
            "sg": sg_avail.slug,
            "user": self.u1.slug,
            "qty": 100,
        }
        response = self.client.post(url, data, **auth_headers)
        self.assertContains(
            response, "Integer must be between 1 and 1.",
            status_code=status.HTTP_400_BAD_REQUEST
        )
        self.assertEqual(Device.objects.count(), 1)

        data = {
            "sg": sg_avail.slug,
            "user": self.u1.slug,
            "qty": -1,
        }
        response = self.client.post(url, data, **auth_headers)
        self.assertContains(
            response, "Integer must be between 1 and 1.",
            status_code=status.HTTP_400_BAD_REQUEST
        )
        self.assertEqual(Device.objects.count(), 1)

    def test_device_list_keys(self):
        url = reverse('manufacturingdata-list')
        auth_headers = {
            'HTTP_AUTHORIZATION': 'Api-Key {}'.format(self.generated_key_o2)
        }
        device = Device.objects.create_device(
            project=self.p1, label='d1', sg=self.sg1,
            template=self.dt1, created_by=self.u1
        )
        key1 = DeviceKey.objects.create_device(
            slug=device.slug, type="MQTT", secret="abc", downloadable=True, created_by=self.u1
        )
        key2 = DeviceKey.objects.create_device(
            slug=device.slug, type="SSH", secret="efg", downloadable=False, created_by=self.u1
        )

        response = self.client.get(url, **auth_headers)
        data = json.loads(response.content.decode())
        self.assertEqual(data["count"], 1)
        self.assertIsNone(data["results"][0].get("keys"))

        url = url + "?keys=1"
        response = self.client.get(url, **auth_headers)
        data = json.loads(response.content.decode())
        self.assertEqual(data["count"], 1)
        self.assertIsNotNone(data["results"][0].get("keys"))
        self.assertEqual(len(data["results"][0]["keys"]), 1)
        self.assertContains(response, key1.secret)
        self.assertNotContains(response, key2.secret)
