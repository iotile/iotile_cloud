import json

import jwt

from django.contrib.auth import get_user_model
from django.core import mail

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.reverse import reverse
from rest_framework.test import APIClient, APITestCase

from ..api_views import *
from ..models import *
from ..serializers import AccountSerializer
from ..tasks import *

user_model = get_user_model()

class AccountAPITests(APITestCase):

    def setUp(self):
        self.u1 = user_model.objects.create_superuser(username='user1', email='user1@foo.com', password='pass')
        self.u1.is_active = True
        self.u1.is_staff = True
        self.u1.name = 'User One'
        self.u1.save()
        self.u2 = user_model.objects.create_user(username='user2', email='user2@foo.com', password='pass')
        self.u3 = user_model.objects.create_user(username='user3', email='user3@foo.com', password='pass')
        self.token1 = Token.objects.create(user=self.u1)
        self.token2 = Token.objects.create(user=self.u2)

    def tearDown(self):
        user_model.objects.all().delete()
        Token.objects.all().delete()

    def test_create_account(self):
        """
        Ensure we can create a new account object.
        """
        url = reverse('account-list')
        data = {'username':'user.new',
                'email':'user.new@foo.com',
                'password':'pass',
                'confirm_password':'pass'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse('password' in response.data)
        self.assertFalse('confirm_password' in response.data)
        self.assertEqual(response.data['username'], data['username'])
        self.assertEqual(response.data['email'], data['email'])
        self.assertEqual(response.data['slug'], 'usernew')

        ok = self.client.login(email='user.new@foo.com', password='pass')
        self.assertFalse(ok)

        response = self.client.get(url, data={'format': 'json'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        user = Account.objects.get(email=data['email'])
        user.is_active = True
        user.save()

        ok = self.client.login(email='user.new@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, data={'format': 'json'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads((response.content).decode())
        self.assertEqual(deserialized['count'], 1)

        url = reverse('account-detail', kwargs={'slug':'usernew'})
        resp = self.client.get(url, data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertEqual(resp.data['username'], u'user.new')
        self.assertEqual(resp.data['slug'], u'usernew')

        self.client.logout()

    def test_list_account(self):
        """
        Ensure we can create a new account object.
        """
        url = reverse('account-list')

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, data={'format': 'json'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads((response.content).decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.get(url, data={'format': 'json', 'staff': 1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads((response.content).decode())
        self.assertEqual(deserialized['count'], 3)

        self.client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        response = self.client.get(url, data={'format': 'json'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads((response.content).decode())
        self.assertEqual(deserialized['count'], 1)

        response = self.client.get(url+'?staff=1', data={'format': 'json'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads((response.content).decode())
        self.assertEqual(deserialized['count'], 1)

        self.client.logout()

    def test_GET_Account(self):

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)
        url = reverse('account-detail', kwargs={'slug':'user1'})
        resp = self.client.get(url, data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertEqual(resp.data['username'], u'user1')
        self.assertEqual(resp.data['email'], u'user1@foo.com')
        self.assertFalse('token' in resp.data)
        self.client.logout()

    def test_PATCH_Account(self):

        url = reverse('account-detail', kwargs={'slug':'user1'})

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['slug'], 'user1')
        self.assertEqual(resp.data['username'], 'user1')
        self.assertEqual(resp.data['email'], 'user1@foo.com')
        self.assertEqual(resp.data['name'], 'User One')
        self.assertEqual(resp.data['tagline'], '')

        new_tagline = 'Awesome'
        data = {'tagline':new_tagline}

        resp = self.client.patch(url, data=data, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.get(url, data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['tagline'], new_tagline)

    def test_GET_Accounts(self):

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)
        url = reverse('account-list')
        resp = self.client.get(url, data={'format': 'json', 'staff': 1})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 3)

        slugs = [obj['slug'] for obj in deserialized['results']]
        emails = [obj['email'] for obj in deserialized['results']]
        self.assertTrue('user1' in slugs)
        self.assertTrue('user2' in slugs)
        self.assertTrue('user3' in slugs)
        self.assertTrue('user1@foo.com' in emails)
        self.assertTrue('user2@foo.com' in emails)
        self.assertTrue('user3@foo.com' in emails)

        self.assertFalse('token' in deserialized['results'][0])
        self.client.logout()

    def test_basic_POST_Account(self):


        url = reverse('account-list')
        resp = self.client.post(url, {'username':'user4',
                                      'email':'user4@foo.com',
                                      'password':'pass',
                                      'confirm_password':'pass'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        u4 = user_model.objects.get(slug='user4')
        u4.is_active = True
        u4.save()
        ok = self.client.login(email='user4@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deserialized = json.loads(resp.content.decode())
        self.assertEqual(deserialized['count'], 1)
        self.client.logout()

        # No duplicates
        data = {'username':'user4',
                'email':'user4@foo.com',
                'password':'pass',
                'confirm_password':'pass'}

        resp = self.client.post(url, data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        data['username'] = 'user5'
        resp = self.client.post(url, data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        data['username'] = 'user4'
        data['email'] = 'user5@foo.com'
        resp = self.client.post(url, data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        data['username'] = 'user5'
        resp = self.client.post(url, data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        data['username'] = 'user6'
        data['email'] = 'user6@foo.com'
        data['confirm_password'] = 'pass1'
        resp = self.client.post(url, data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        data['tagline'] = 'Awesome'
        data['name'] = 'User One'
        data['confirm_password'] = 'pass'
        resp = self.client.post(url, data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_basic_POST_NoPassword(self):

        url = reverse('account-list')
        resp = self.client.post(url, {'username':'user4', 'email':'user4@foo.com'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_basic_POST_VerifiedEmail(self):

        url = reverse('account-list')
        data = {'username':'user4',
                'email':'user4@foo.com',
                'password':'pass',
                'confirm_password':'pass',
                'verified_email': True}

        resp = self.client.post(url, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        # Regular users cannot automatically verifed their email
        self.assertFalse(EmailAddress.objects.filter(email=data['email'], verified=True).exists())
        user = Account.objects.get(email=data['email'])
        self.assertFalse(user.is_active)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        data['username'] = 'user5'
        data['email'] = 'user5@foo.com'

        resp = self.client.post(url, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        # Staff users can verify emails
        self.assertTrue(EmailAddress.objects.filter(email=data['email'], verified=True).exists())
        user = Account.objects.get(email=data['email'])
        self.assertTrue(user.is_active)

        self.client.logout()


    def test_api_jwt(self):

        url = reverse('api-jwt-auth')
        u4 = user_model.objects.create_user(username='user4', email='user4@foo.com', password='pass')
        u4.is_active = False
        u4.save()

        resp = self.client.post(url, {'email':'user4@foo.com', 'password':'pass'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        u4.is_active = True
        u4.save()

        resp = self.client.post(url, {'username':'user4@foo.com', 'password':'pass'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue('token' in resp.data)
        token = resp.data['token']
        #print(token)

        #encoded = jwt.encode({'some': 'payload'}, settings.SECRET_KEY, algorithm='HS256')
        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        #print(str(decoded))
        self.assertEqual(decoded['user_id'], u4.id)
        self.assertEqual(decoded['email'], 'user4@foo.com')
        self.assertEqual(decoded['username'], 'user4')

        verification_url = reverse('api-jwt-verify')
        resp = self.client.post(verification_url, {'token': token}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.post(verification_url, {'token': 'abc'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='JWT ' + 'abc')
        resp = client.get('/api/v1/account/', data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        client.credentials(HTTP_AUTHORIZATION='JWT ' + token)
        resp = client.get('/api/v1/account/', data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = client.get('/api/v1/account/{0}/'.format(u4.slug), data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        token2 = u4.jwt_token
        #self.assertEqual(token, token2)

    def test_api_jwt_verify(self):

        url_auth = reverse('api-jwt-auth')
        url_verify = reverse('api-jwt-verify')
        u4 = user_model.objects.create_user(username='user4', email='user4@foo.com', password='pass')
        u4.is_active = True
        u4.save()

        resp = self.client.post(url_auth, {'username':'user4@foo.com', 'password':'pass'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue('token' in resp.data)
        token = resp.data['token']

        resp = self.client.post(url_verify, {'token': token}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.post(url_verify, {'token': 'abc'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_api_jwt_refresh(self):

        url_auth = reverse('api-jwt-auth')
        url_refresh = reverse('api-jwt-refresh')
        u4 = user_model.objects.create_user(username='user4', email='user4@foo.com', password='pass')
        u4.is_active = True
        u4.save()

        resp = self.client.post(url_auth, {'username':'user4@foo.com', 'password':'pass'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue('token' in resp.data)
        token = resp.data['token']
        decoded1 = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])

        resp = self.client.post(url_refresh, {'token': token}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue('token' in resp.data)
        token = resp.data['token']
        decoded2 = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        self.assertEqual(decoded1['username'], decoded2['username'])

    def test_login_api(self):

        client = self.client

        url1 = reverse('api-jwt-auth')

        # This is the django rest framework provided function
        resp = client.post(url1, {'username':'user1@foo.com', 'password':'pass'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue('token' in resp.data)
        jwt_token = resp.data['token']

        client.logout()

        url2 = reverse('api-login')
        resp = client.post(url2, {'email':'user1@foo.com', 'password':'pass'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue('token' in resp.data)
        self.assertTrue('jwt' in resp.data)
        self.assertEqual(resp.data['token'], self.token1.key)

        client.logout()

        resp = client.post(url1, {'username':'user1@foo.com'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        resp = client.post(url1, {'username':'user101@foo.com', 'password':'pass'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        resp = client.post(url2, {'email':'user1@foo.com'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        resp = client.post(url2, {'email':'user101@foo.com', 'password':'pass'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        # Test that we cannot login if not Active
        u5 = user_model.objects.create_user(username='user5', email='user5@foo.com', password='pass')
        u5.is_active = False
        u5.save()
        resp = client.post(url1, {'username':'user5@foo.com', 'password':'pass'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        resp = client.post(url2, {'email':'user5@foo.com', 'password':'pass'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_info_api(self):

        url = reverse('api-user-info')

        resp = self.client.get(url, data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertEqual(resp.data['tagline'], '')
        self.assertEqual(resp.data['name'], 'User One')
        self.assertEqual(resp.data['username'], 'user1')
        self.assertEqual(resp.data['email'], 'user1@foo.com')

    def test_PUT_Account(self):

        url = reverse('account-detail', kwargs={'slug':'user1'})

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = self.client.get(url, data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['slug'], 'user1')
        self.assertEqual(resp.data['username'], 'user1')
        self.assertEqual(resp.data['email'], 'user1@foo.com')
        self.assertEqual(resp.data['name'], 'User One')
        self.assertEqual(resp.data['tagline'], '')

        new_tagline = 'Awesome'
        data = {'email':self.u1.email,
                'username':self.u1.username,
                'name':'User One',
                'tagline':new_tagline}

        resp = self.client.put(url, data=data, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.get(url, data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['tagline'], data['tagline'])
        self.assertEqual(resp.data['username'], data['username'])
        self.assertEqual(resp.data['name'], data['name'])
        self.assertEqual(resp.data['email'], data['email'])

    def test_logout_api(self):

        url = reverse('api-login')
        client = self.client

        resp = client.post(url, {'email':'user1@foo.com', 'password':'pass'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue('token' in resp.data)
        self.assertEqual(resp.data['token'], self.token1.key)

        url = reverse('api-logout')
        resp = client.post(url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_set_password_api(self):

        url = '/api/v1/account/user2/set_password/'
        client = self.client
        ok = self.u2.check_password('pass')
        self.assertTrue(ok)

        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        resp = client.post(url, {'password': 'pass2'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        client.logout()

        ok = self.client.login(email='user2@foo.com', password='pass')
        self.assertTrue(ok)

        resp = client.post(url, {'password':'pass2'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.u2 = Account.objects.get(slug='user2')
        ok = self.u2.check_password('pass')
        self.assertFalse(ok)
        ok = self.u2.check_password('pass2')
        self.assertTrue(ok)

        client.logout()

    def test_reset_password_api(self):
        url = reverse('reset-password')

        resp = self.client.post(url, {'email': 'user1@foo.com'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, '[IOTile Cloud by Arch] Password Reset E-mail')

        resp = self.client.post(url, {'email': 'invalidemail@foo.com'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # No email sent
        self.assertEqual(len(mail.outbox), 1)

    def test_spaces_in_username(self):
        # Create user
        url = reverse('account-list')
        payload = {'username':'user 5',
                   'email':'user5@foo.com',
                   'password':'pass',
                   'confirm_password':'pass'}
        resp = self.client.post(url, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        payload['username'] = "user5"
        resp = self.client.post(url, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['slug'], 'user5')
        self.assertEqual(resp.data['username'], 'user5')

        # List
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok, msg=str(ok))

        # Edit an existing user to a username with a space
        url = reverse('account-detail', kwargs={'slug':'user1'})
        data = {'username': 'user 1'}
        resp = self.client.patch(url, data=data, format='json')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        resp = self.client.get(url, data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_duplicate_username(self):
        ok = self.client.login(email='user1@foo.com', password='pass')
        self.assertTrue(ok)

        url = reverse('account-detail', kwargs={'slug':'user1'})
        resp = self.client.get(url, data={'format': 'json'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['slug'], 'user1')
        self.assertEqual(resp.data['username'], 'user1')

        # Create user with duplicate username
        url = reverse('account-list')
        payload = {'username':'user1',
                   'email':'user5@foo.com',
                   'password':'pass',
                   'confirm_password':'pass'}
        resp = self.client.post(url, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Change it to a new username and verify that it is successful
        payload['username'] = "user5"
        resp = self.client.post(url, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['slug'], 'user5')
        self.assertEqual(resp.data['username'], 'user5')

        # Edit the user with a duplicate username
        url = reverse('account-detail', kwargs={'slug':'user1'})
        resp = self.client.get(url, data={'format': 'json'})
        data = {'username': "user5"}
        resp = self.client.patch(url, data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
