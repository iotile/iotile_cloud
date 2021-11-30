from django.conf import settings
from django.contrib.sites.models import Site
from django.core.mail import EmailMessage, mail_admins
from django.core.management.base import BaseCommand


class Command(BaseCommand):


    def handle(self, *args, **options):

        site = Site.objects.first()

        print('Test: Emailing Admins')
        mail_admins(
            subject='Test: Email to Admins',
            message='This is an email test from {0} to the Django Admins'.format(str(Site.objects.first()))
        )

        print('Test: Emailing Users')
        email = EmailMessage(
            subject='Test: General Emails',
            body='Email test from {0}'.format(site.domain),
            to=['admin@test.com', ],
            headers={'Message-ID': 'IOTile Cloud Email Test'},
        )
        email.send(fail_silently=True)

        print('Email Test Completed')



