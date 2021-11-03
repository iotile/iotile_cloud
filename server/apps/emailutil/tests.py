import pytest

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.utils.test_util import TestMixin
from apps.org.models import Org, OrgMembership

from .utils import EmailRecipientHelper

user_model = get_user_model()


class EmailHelperTestCase(TestMixin, TestCase):
    def setUp(self):
        self.usersTestSetup()
        self.u4 = user_model.objects.create_user(username='user4', email='user4@foo.com', password='pass')
        self.u4.is_active = True
        self.u4.save()
        self.o1 = Org.objects.create_org(name='Vendor', created_by=self.u1, is_vendor=True)
        self.o2 = Org.objects.create_org(name='Org 1', created_by=self.u2)
        self.o2.register_user(self.u3)
        self.o3 = Org.objects.create_org(name='Org 2', created_by=self.u4)

    def tearDown(self):
        self.orgTestTearDown()
        self.userTestTearDown()

    def testEmailHelper(self):
        self.assertTrue(self.u1.is_staff)
        self.assertTrue(self.o2.is_admin(self.u2))
        self.assertTrue(self.o2.has_access(self.u2))
        self.assertTrue(self.o2.has_access(self.u3))
        self.assertFalse(self.o2.has_access(self.u4))

        helper = EmailRecipientHelper()

        r_list = ['staff:all']
        emails = helper.get_emails_from_recipient_list(r_list, self.o2)
        self.assertEqual(len(emails), 1)
        self.assertIn(self.u1.email, emails)

        r_list = ['staff:other']
        with pytest.raises(AssertionError):
            helper.get_emails_from_recipient_list(r_list, self.o2)

        r_list = ['org:admin']
        emails = helper.get_emails_from_recipient_list(r_list, self.o2)
        self.assertEqual(len(emails), 1)
        self.assertIn(self.u2.email, emails)

        r_list = ['org:all']
        emails = helper.get_emails_from_recipient_list(r_list, self.o2)
        self.assertEqual(len(emails), 2)
        self.assertIn(self.u2.email, emails)
        self.assertIn(self.u3.email, emails)

        r_list = ['user:user2', 'user:user3']
        emails = helper.get_emails_from_recipient_list(r_list, self.o2)
        self.assertEqual(len(emails), 2)
        self.assertIn(self.u2.email, emails)
        self.assertIn(self.u3.email, emails)

        r_list = ['user:user2', 'email:joe@test.com']
        emails = helper.get_emails_from_recipient_list(r_list, self.o2)
        self.assertEqual(len(emails), 2)
        self.assertIn(self.u2.email, emails)
        self.assertIn('joe@test.com', emails)

        # Check that we remove duplicates
        r_list = ['user:user2', 'user:user2']
        emails = helper.get_emails_from_recipient_list(r_list, self.o2)
        self.assertEqual(len(emails), 1)
        self.assertIn(self.u2.email, emails)

        # Check users with tricky slugs
        u5 = user_model.objects.create_user(username='User+5', email='user+5@foo.com', password='pass')
        u5.is_active = True
        u5.save()
        self.o2.register_user(u5)
        r_list = ['user:user5']
        emails = helper.get_emails_from_recipient_list(r_list, self.o2)
        self.assertEqual(len(emails), 1)
        self.assertIn(u5.email, emails)

    def testDeactivateMembership(self):
        helper = EmailRecipientHelper()
        o2u2 = OrgMembership.objects.get(user=self.u2, org=self.o2)

        o2u2.is_active = False
        o2u2.save()

        r_list = ['org:all']
        emails = helper.get_emails_from_recipient_list(r_list, self.o2)
        self.assertNotIn(self.u2.email, emails, str(r_list) + ' qualifier')

        r_list = ['org:admin']
        emails = helper.get_emails_from_recipient_list(r_list, self.o2)
        self.assertNotIn(self.u2.email, emails, str(r_list) + ' qualifier')

        r_list = ['staff:all']
        self.u2.is_staff = True
        self.u2.save()
        emails = helper.get_emails_from_recipient_list(r_list, self.o2)
        self.assertIn(self.u2.email, emails, str(r_list) + ' qualifier')
        self.u2.is_staff = False
        self.u2.save()

        r_list = ['user:%s' % self.u2.slug]
        emails = helper.get_emails_from_recipient_list(r_list, self.o2)
        self.assertNotIn(self.u2.email, emails, str(r_list) + ' qualifier')

    def testDeactivateUser(self):
        helper = EmailRecipientHelper()

        self.u2.is_active = False
        self.u2.save()

        r_list = ['org:all']
        emails = helper.get_emails_from_recipient_list(r_list, self.o2)
        self.assertNotIn(self.u2.email, emails, str(r_list) + ' qualifier')

        r_list = ['org:admin']
        emails = helper.get_emails_from_recipient_list(r_list, self.o2)
        self.assertNotIn(self.u2.email, emails, str(r_list) + ' qualifier')

        r_list = ['staff:all']
        self.u2.is_staff = True
        self.u2.save()
        emails = helper.get_emails_from_recipient_list(r_list, self.o2)
        self.assertNotIn(self.u2.email, emails, str(r_list) + ' qualifier')
        self.u2.is_staff = False
        self.u2.save()

        r_list = ['user:%s' % self.u2.slug]
        emails = helper.get_emails_from_recipient_list(r_list, self.o2)
        self.assertNotIn(self.u2.email, emails, str(r_list) + ' qualifier')
