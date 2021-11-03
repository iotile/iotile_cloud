import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.conf import settings

from rest_framework import status

from apps.org.models import Org
from apps.project.models import Project

user_model = get_user_model()

class MainTestCase(TestCase):
    """
    Fixure includes:
    """
    #fixtures = ['testdb_main.json']
    databases = '__all__'

    def setUp(self):
        self.u1 = user_model.objects.create_superuser(username='User1', email='user1@foo.com', password='pass')
        self.u1.is_active = True
        self.u1.save()
        self.u2 = user_model.objects.create_user(username='User2', email='user2@foo.com', password='pass')
        self.u2.is_active = True
        self.u2.save()
        self.u3 = user_model.objects.create_user(username='User3', email='user3@foo.com', password='pass')
        self.u3.is_active = True
        self.u3.save()
        return

    def tearDown(self):
        Org.objects.all().delete()
        user_model.objects.all().delete()

    def testPages(self):
        response = self.client.get(reverse('about'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get('/api/v1/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.login(email='user1@foo.com', password='pass')
        response = self.client.get('/api/v1/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.logout()

    def testOnboard(self):
        self.client.login(email='user2@foo.com', password='pass')

        response = self.client.get('/', {})
        self.assertRedirects(response, expected_url='/onboard1', status_code=302, target_status_code=200)
        response = self.client.get('/onboard1', {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get('/onboard2', {})
        self.assertRedirects(response, expected_url='/onboard1', status_code=302, target_status_code=200)
        response = self.client.get('/onboard3', {})
        self.assertRedirects(response, expected_url='/onboard1', status_code=302, target_status_code=200)
        response = self.client.get('/onboard4', {})
        self.assertRedirects(response, expected_url='/onboard1', status_code=302, target_status_code=200)

        org = Org.objects.create_org(name='My Org', created_by=self.u2)
        response = self.client.get('/', {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get('/onboard1', {})
        self.assertRedirects(response, expected_url='/onboard1/done', status_code=302, target_status_code=200)
        response = self.client.get('/onboard2', {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get('/onboard3', {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get('/onboard4', {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        Project.objects.create(name='My Project', org=org, created_by=self.u2)
        response = self.client.get('/', {})
        response = self.client.get('/onboard1', {})
        self.assertRedirects(response, expected_url='/onboard1/done', status_code=302, target_status_code=200)
        response = self.client.get('/onboard2', {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get('/onboard3', {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get('/onboard4', {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testOrgDuplicates(self):
        existing_org = Org.objects.create(name='Popular Org', created_by=self.u2)

        u4 = user_model.objects.create_user(username='User4', email='user4@foo.com', password='pass')
        u4.is_active = True
        u4.save()

        ok = self.client.login(email='user4@foo.com', password='pass')
        self.assertEqual(ok, True)
        self.assertEqual(Org.objects.count(), 1)
        url = reverse('onboard-step-org')
        payload = {'name': 'Popular Org'}

        self.assertEqual(existing_org.slug, 'popular-org')

        # Name duplicates not allowed
        resp = self.client.post(url, payload, format='json')
        self.assertContains(resp, 'Company Name already exists', status_code=200)
        self.assertEqual(Org.objects.count(), 1)

        # Different Name, but duplicate slug
        payload = {'name': 'Popular-Org'}
        self.assertContains(resp, 'Company Name already exists', status_code=200)
        self.assertEqual(Org.objects.count(), 1)

    def testServerInfoApi(self):
        response = self.client.get(reverse('api-server'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['stage'], settings.SERVER_TYPE)

        self.client.login(email='user2@foo.com', password='pass')

        response = self.client.get(reverse('api-server'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testDbStatsApi(self):
        url = reverse('api-db-stats')

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.login(email='user2@foo.com', password='pass')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.client.logout()

        self.client.login(email='user1@foo.com', password='pass')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deserialized = json.loads(response.content.decode())
        self.assertEqual(deserialized['days'], 'all')
        self.client.logout()




