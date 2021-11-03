from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from rest_framework import status

from apps.streamfilter.models import *
from apps.utils.test_util import TestMixin

from ..models import *

user_model = get_user_model()


class StreamNoteTestCase(TestMixin, TestCase):

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p2, label='d2', template=self.dt1, created_by=self.u3)

    def tearDown(self):
        StreamNote.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

    def testAccess(self):
        """
        Ensure we can call GET note pages
        """
        n1 = StreamNote.objects.create(
            target_slug=self.pd1.slug, timestamp=timezone.now(), note='Note 1', created_by=self.u2
        )

        list_url = reverse('streamnote:list', kwargs={
            'slug': self.pd1.slug
        })
        add_url = reverse('streamnote:add', kwargs={
            'slug': self.pd1.slug
        })
        attachment_url = reverse('streamnote:upload', kwargs={
            'pk': n1.pk
        })

        self.assertTrue(self.pd1.has_access(self.u1))
        self.assertTrue(self.pd1.has_access(self.u2))
        self.assertFalse(self.pd1.has_access(self.u3))

        resp = self.client.get(list_url, format='json')
        self.assertRedirects(resp, expected_url='/account/login/?next='+list_url, status_code=302, target_status_code=200)
        resp = self.client.get(add_url, format='json')
        self.assertRedirects(resp, expected_url='/account/login/?next='+add_url, status_code=302, target_status_code=200)
        resp = self.client.get(attachment_url, format='json')
        self.assertRedirects(resp, expected_url='/account/login/?next='+attachment_url, status_code=302, target_status_code=200)

        self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.get(list_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.get(add_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.get(attachment_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()
        self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(list_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(add_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(attachment_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.logout()

    def testGetViews(self):
        """
        Test Note Views
        """
        StreamNote.objects.create(
            target_slug=self.pd1.slug, timestamp=timezone.now(), note='Note 1', created_by=self.u2
        )
        StreamNote.objects.create(
            target_slug=self.pd1.slug, timestamp=timezone.now(), note='Note 2', created_by=self.u1, type='sc'
        )
        StreamNote.objects.create(
            target_slug=self.pd2.slug, timestamp=timezone.now(), note='Note 3', created_by=self.u1, type='sc'
        )

        list_url1 = reverse('streamnote:list', kwargs={'slug': self.pd1.slug})
        list_url2 = reverse('streamnote:list', kwargs={'slug': self.pd2.slug})
        list_url3 = reverse('streamnote:list', kwargs={'slug': 'd--1111-1111-1111-1111'})

        resp = self.client.get(list_url1)
        self.assertRedirects(
            resp, expected_url='/account/login/?next='+list_url1, status_code=302, target_status_code=200
        )

        self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.get(list_url1)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.get(list_url2)
        self.assertContains(resp, 'Note 3', status_code=200)

        self.client.logout()
        self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(list_url1)
        self.assertContains(resp, 'Note 1', status_code=200)
        self.assertContains(resp, 'Note 2', status_code=200)
        resp = self.client.get(list_url2)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.get(list_url3)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testAddViews(self):
        """
        Test that people with no permissions cannot access
        """
        add_url1 = reverse('streamnote:add', kwargs={'slug': self.pd1.slug})
        add_url2 = reverse('streamnote:add', kwargs={'slug': self.pd2.slug})
        add_url3 = reverse('streamnote:add', kwargs={'slug': 'd--1111-1111-1111-1111'})

        resp = self.client.get(add_url1)
        self.assertRedirects(
            resp, expected_url='/account/login/?next='+add_url1, status_code=302, target_status_code=200
        )

        self.client.login(email='user3@foo.com', password='pass')

        resp = self.client.get(add_url1)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.get(add_url2)
        self.assertContains(resp, 'New Note', status_code=200)

        self.client.logout()
        self.client.login(email='user2@foo.com', password='pass')

        resp = self.client.get(add_url2)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.get(add_url3)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.get(add_url1)
        self.assertContains(resp, 'New Note', status_code=200)

        payload = {
            'note': 'Note 1'
        }
        resp = self.client.post(add_url1, payload)
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(StreamNote.objects.count(), 1)
        note = StreamNote.objects.first()
        self.assertEqual(note.note, 'Note 1')
        self.assertEqual(note.target_slug, self.pd1.slug)

        resp = self.client.post(add_url2, payload)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()

    def testMemberPermissions(self):
        """
        Test that peeople with no
        """

        add_url = reverse('streamnote:add', kwargs={'slug': self.pd1.slug})
        list_url = reverse('streamnote:list', kwargs={'slug': self.pd1.slug})

        self.client.login(email='user3@foo.com', password='pass')
        self.pd1.org.de_register_user(self.u3, delete_obj=True)
        membership = self.pd1.org.register_user(self.u3, role='m1')
        membership.permissions['can_read_notes'] = False
        membership.permissions['can_access_classic'] = True
        membership.save()
        self.assertFalse(self.pd1.org.has_permission(self.u3, 'can_read_notes'))
        self.assertTrue(self.pd1.org.has_permission(self.u3, 'can_access_classic'))

        resp = self.client.get(add_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(list_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        membership.permissions['can_access_classic'] = False
        membership.save()

        resp = self.client.get(add_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.logout()
