import json
from django.test import TestCase, override_settings
from django.core.cache import cache  # default cache

from apps.utils.test_util import TestMixin
from rest_framework.test import APITestCase
from rest_framework.reverse import reverse
from rest_framework import status
from apps.vartype.models import *

class VarTypeTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.projectTemplateTestSetup()

    def tearDown(self):
        VarType.objects.all().delete()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testBasicCreate(self):
        vt = VarType.objects.create(name="test vartype",
                                    storage_units_full="test unit",
                                    created_by=self.u1)
        self.assertEqual(vt.stream_data_type, '00')
        self.assertEqual(VarType.objects.all().count(), 1)

    def testVarTypeIsEncoded(self):
        vt = VarType.objects.create(name="test vartype",
                                    storage_units_full="test unit",
                                    created_by=self.u1)
        self.assertEqual(VarType.objects.all().count(), 1)
        self.assertFalse(vt.is_encoded)

        # Test Signals (post_save and pre_delete)
        decoder = VarTypeDecoder.objects.create(var_type=vt, packet_info={}, created_by=self.u1)
        vt = VarType.objects.first()
        self.assertTrue(vt.is_encoded)

        decoder.delete()
        vt = VarType.objects.first()
        self.assertFalse(vt.is_encoded)

    def testVarTypeHasSchema(self):
        vt = VarType.objects.create(name="test vartype",
                                    storage_units_full="test unit",
                                    created_by=self.u1)
        self.assertEqual(VarType.objects.all().count(), 1)
        self.assertFalse(vt.is_encoded)

        # Test Signals (post_save and pre_delete)
        schema = VarTypeSchema.objects.create(var_type=vt, keys={}, created_by=self.u1)
        vt = VarType.objects.first()
        self.assertFalse(vt.is_encoded)
        self.assertTrue(vt.has_schema)

        schema.delete()
        vt = VarType.objects.first()
        self.assertFalse(vt.has_schema)


class VarTypeAPITestCase(TestMixin, APITestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()

    def tearDown(self):
        VarType.objects.all().delete()
        self.orgTestTearDown()
        self.userTestTearDown()

    @override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    def testPost(self):
        url = reverse('vartype-list')
        payload = {
            "name": "test vartype",
            "storage_units_full": "test unit"
        }

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # staff permission
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(VarType.objects.count(), 1)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        # read only
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def testVarTypeDecoderSchemaGet(self):
        vt = VarType.objects.create(name="test vartype",
                                    storage_units_full="test unit",
                                    created_by=self.u1)
        VarTypeDecoder.objects.create(var_type=vt, packet_info={
            'foo': 'a'
        }, created_by=self.u1)
        VarTypeSchema.objects.create(var_type=vt, keys={
            'bar': 'b'
        }, created_by=self.u1)
        url = reverse('vartype-detail', kwargs={'slug': vt.slug})

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        # read only
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertTrue('decoder' in deserialized)
        self.assertTrue('schema' in deserialized)
        self.assertTrue('packet_info' in deserialized['decoder'])
        self.assertTrue('keys' in deserialized['schema'])
        self.assertEqual(deserialized['decoder']['packet_info']['foo'], 'a')
        self.assertEqual(deserialized['schema']['keys']['bar'], 'b')

        self.client.logout()



