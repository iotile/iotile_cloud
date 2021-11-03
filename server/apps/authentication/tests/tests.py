import json

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from rest_framework.reverse import reverse

from ..models import *
from ..tasks import *
from ..api_views import *
from ..serializers import AccountSerializer

user_model = get_user_model()

class MainTestCase(TestCase):
    """
    Fixure includes:
    """
    #fixtures = ['testdb_main.json']

    def setUp(self):
        self.u1 = user_model.objects.create_superuser(username='user1', email='user1@foo.com', password='pass')
        self.u1.name = 'User One'
        self.u1.is_active = True
        self.u1.is_staff = True
        self.u1.save()
        self.u2 = user_model.objects.create_user(username='user2', email='user2@foo.com', password='pass')
        self.u2.name = 'User G Two'
        self.u2.time_zone = 'America/Chicago'
        self.u2.save()
        self.u3 = user_model.objects.create_user(username='user3', email='user3@foo.com', password='pass')
        self.assertEqual(user_model.objects.count(), 3)
        self.token1 = Token.objects.create(user=self.u1)
        self.token2 = Token.objects.create(user=self.u2)

    def tearDown(self):
        user_model.objects.all().delete()
        self.assertEqual(user_model.objects.count(), 0)
        Token.objects.all().delete()
        EmailAddress.objects.all().delete()

    def test_url(self):
        self.assertEqual(self.u3.get_absolute_url(), '/account/{0}/'.format(self.u3.username))

    def test_full_short_names(self):
        self.assertEqual(self.u3.get_full_name(), u'')
        self.assertEqual(self.u3.get_short_name(), self.u3.username)
        self.assertEqual(self.u2.get_full_name(), self.u2.name)
        self.assertEqual(self.u2.get_short_name(), u'User')

    def test_get_admin(self):
        admin = Account.objects.get_admin()
        self.assertEqual(admin.slug, 'user1')

    def test_basic_gets(self):
        ok = self.client.login(email='user1@foo.com', password='pass')

        profile_url = reverse('account_detail', kwargs={'slug':'user1'})
        resp = self.client.get(profile_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # account should also redirect to the above
        url = reverse('account_redirect')
        resp = self.client.get(url, format='json')
        self.assertRedirects(resp, expected_url=profile_url, status_code=302, target_status_code=200)

        url = reverse('account_edit', kwargs={'slug':'user1'})
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # TODO: What's the URL namespace for django-allauth
        # TODO: Enable test when a social login is added
        '''
        url = '/account/email/'
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        url = '/account/social/connections/'
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        url = '/account/password/change/'
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        '''

    def test_email_as_username(self):
        email = 'user@example.com'
        u = user_model.objects.create_user(username=email, email=email, password='pass')
        u.is_active = True
        u.save()

        self.client.login(email=email, password='pass')

        profile_url = reverse('account_detail', kwargs={'slug':u.slug})
        resp = self.client.get(profile_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # account should also redirect to the above
        url = reverse('account_redirect')
        resp = self.client.get(url, format='json')
        self.assertRedirects(resp, expected_url=profile_url, status_code=302, target_status_code=200)

        url = reverse('account_edit', kwargs={'slug':u.slug})
        resp = self.client.get(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_no_slug_conflicts(self):
        u1 = user_model.objects.create_user(username='User.4', email='user41@foo.com', password='pass')
        self.assertEqual(u1.slug, 'user4')
        u2 = user_model.objects.create_user(username='User4', email='user42@foo.com', password='pass')
        # Because user4 is taken, it will add a digit until it finds a match
        self.assertEqual(u2.slug, 'user40')

    def test_api_token(self):

        url = reverse('api-token')
        u4 = user_model.objects.create_user(username='User4', email='user4@foo.com', password='pass')
        u4.is_active = True
        u4.save()

        token = u4.drf_token

        resp = self.client.get(url, data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        ok = self.client.login(email='user4@foo.com', password='pass')
        self.assertTrue(ok)
        resp = self.client.get(url, data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(len(deserialized), 2)
        jwt_token = u4.jwt_token
        self.assertEqual(deserialized['jwt'], jwt_token)
        self.assertEqual(deserialized['token'], str(token))

        resp = self.client.get(url, data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_serializer(self):
        account = Account.objects.latest('created_at')
        serialized_account = AccountSerializer(account)
        email = serialized_account.data.get('email')
        username = serialized_account.data.get('username')
        self.assertEqual(username, 'user3')
        self.assertEqual(email, 'user3@foo.com')

    def testTimeZone(self):
        #tzname = request.session.get('django_timezone')
        response = self.client.get('/account/login/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # If not loggedin, no timezone in session
        session = self.client.session
        self.assertFalse('django_timezone' in session)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)
        response = self.client.get('/onboard1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Default Time zone
        session = self.client.session
        self.assertTrue('django_timezone' in session)
        self.assertEqual(session["django_timezone"], timezone.get_default_timezone_name())

        self.client.logout()

        u4 = user_model.objects.create_user(username='user4', email='user4@foo.com', password='pass')
        u4.name = 'New York Dude'
        u4.time_zone = 'America/New_York'
        u4.is_active = True
        u4.save()

        ok = self.client.login(email='user4@foo.com', password='pass')
        self.assertTrue(ok)
        response = self.client.get('/onboard1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Default Time zone
        session = self.client.session
        self.assertTrue('django_timezone' in session)
        self.assertEqual(session["django_timezone"], timezone.get_current_timezone_name())
        self.assertEqual(timezone.get_current_timezone_name(), 'America/New_York')

        self.client.logout()

    def test_registration_notification(self):
        send_new_user_notification(self.u1.id, self.u1.username, self.u1.email)

    def test_spaces_in_username(self):

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)
        url = self.u2.get_edit_url()
        payload = {
            'username': 'user 2new',
            'time_zone': 'UTC'
        }
        response = self.client.post(url, payload)
        self.assertContains(response, text='Username cannot have spaces', status_code=status.HTTP_200_OK)

        payload['username'] = 'user2new'
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        user2 = Account.objects.get(email='user2@foo.com')
        self.assertEqual(user2.username, 'user2new')
