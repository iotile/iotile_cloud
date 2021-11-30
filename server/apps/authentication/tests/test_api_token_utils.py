import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.org.models import AuthAPIKey, Org, OrgMembership
from apps.utils.api_key_utils import get_apikey_object_from_generated_key, get_org_slug_from_apikey
from apps.utils.test_util import TestMixin

user_model = get_user_model()


class APIKeyUtilsTestCase(TestCase):
    # Get AuthAPIKey Object tests

    def setUp(self):
        self.u1 = user_model.objects.create_superuser(username='user1', email='user1@foo.com', password='pass')
        self.u1.is_active = True
        self.u1.is_staff = True
        self.u1.name = 'User One'
        self.u1.save()
        self.o1 = Org.objects.create_org(name='My Org 1', created_by=self.u1)
        self.api_key, self.generated_key = AuthAPIKey.objects.create_key(name="API key unit test", org=self.o1)

    def tearDown(self):
        Org.objects.all().delete()
        OrgMembership.objects.all().delete()
        user_model.objects.all().delete()
        AuthAPIKey.objects.all().delete()

    def testGetKey(self):
        # Retrieve key test
        ret_apikey = get_apikey_object_from_generated_key(self.generated_key)
        self.assertEqual(ret_apikey.name, self.api_key.name)
        self.assertEqual(ret_apikey.org, self.o1)

    def testRevokedKey(self):
        # Revoked key test
        apikey = get_apikey_object_from_generated_key(self.generated_key)
        apikey.revoked = True
        apikey.save()

        ret_apikey = get_apikey_object_from_generated_key(self.generated_key)
        self.assertIsNone(ret_apikey)

    def testInvalidKey(self):
        # Invalid key test
        ret_apikey = get_apikey_object_from_generated_key(None)
        self.assertIsNone(ret_apikey)

        invalid_key = ''
        ret_apikey = get_apikey_object_from_generated_key(invalid_key)
        self.assertIsNone(ret_apikey)

        invalid_key = 'abcdefg.12345'
        ret_apikey = get_apikey_object_from_generated_key(invalid_key)
        self.assertIsNone(ret_apikey)

        invalid_key = 'abcdefg.12345'
        ret_apikey = get_apikey_object_from_generated_key(invalid_key)
        self.assertIsNone(ret_apikey)

    def testTruncatedKey(self):
        # Truncate key before the '.'
        ret_apikey = get_apikey_object_from_generated_key(self.generated_key[0:5])
        self.assertIsNone(ret_apikey)

        truncated_key = self.generated_key.split('.')
        ret_apikey = get_apikey_object_from_generated_key(truncated_key[0])
        self.assertIsNone(ret_apikey)
