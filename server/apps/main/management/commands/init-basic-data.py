import datetime
from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site
from django.db.models import F
from django.db.utils import IntegrityError

from allauth.account.models import EmailAddress

from apps.authentication.models import Account
from apps.org.models import Org, OrgMembership
from apps.org.roles import ORG_ROLE_PERMISSIONS
from apps.devicetemplate.models import DeviceTemplate, DeviceSlot
from apps.projecttemplate.models import ProjectTemplate
from apps.project.models import Project
from apps.physicaldevice.models import Device
from apps.sensorgraph.models import *
from apps.stream.models import StreamVariable, StreamId
from apps.vartype.models import *
from apps.widget.models import *
from apps.physicaldevice.claim_utils import device_claim
from apps.staff.worker.dbstats import METRIC_ID

NUM_TEST_DEVICES = 128


def _create_project_templates(admin_user, org):
    templates = {}
    print('Creating Project Templates')
    ptemplate1 = ProjectTemplate.objects.create_template(
        name='Default Template',
        org=org,
        major_version=1,
        created_by=admin_user
    )
    master1 = Project.objects.master_project_for_template(ptemplate1)
    templates['default'] = ptemplate1


    return templates


def _create_vendor_org(admin_user):
    # Most create all external vendors as well
    for vendor in ['WellDone']:
        Org.objects.create_org(name=vendor, is_vendor=True, created_by=admin_user)
    # Now create Arch's vendor org
    org = Org.objects.create_org(name='Arch Systems', is_vendor=True, created_by=admin_user)
    for u in Account.objects.all():
        if u != admin_user:
            OrgMembership.objects.create(user=u, org=org, is_admin=True)
    return org


class Command(BaseCommand):
    _admin = None

    def _create_super_users(self):
        for user in getattr(settings, 'ADMINS'):
            username = user[0].replace(' ', '')
            email = user[1]
            password = 'admin'
            print('Creating account for %s (%s)' % (username, email))
            admin = Account.objects.create_superuser(email=email, username=username, password=password)
            admin.is_active = True
            admin.is_admin = True
            admin.save()
            EmailAddress.objects.create(email=email, user=admin, verified=True, primary=True)

    def _fix_site_record(self):
        strato = Site.objects.first()
        if strato:
            print('No Site record. Creating one')
            strato.domain = settings.DOMAIN_NAME
            strato.name = settings.SITE_NAME
            strato.save()
        else:
            print('No Site record. Creating one')
            Site.objects.create(domain=settings.DOMAIN_NAME, name=settings.SITE_NAME)

    def _create_test_devices(self, org):
        template = DeviceTemplate.objects.create_template(external_sku='InternalTestingTemplate',
                                                          internal_sku='arch0000',
                                                          major_version=1,
                                                          org=org, active=False,
                                                          released_on=datetime.datetime.utcnow(),
                                                          created_by=self._admin)
        for i in range(NUM_TEST_DEVICES):
            label = 'InternalDevice{0}'.format(i + 1)
            Device.objects.create_device(label=label, project=None, template=template,
                                         created_by=self._admin, active=False)

        # Activate demo devices
        Device.objects.filter(id__in=range(0x50, 0x6f)).update(active=True, label='Reserved for Demos')

    '''
    def _create_social_accounts(self, site):
        # For test/stage, also create dummy Facebook setup
        print('Creating Dummy SocialApp for Facebook')
        app = SocialApp.objects.create(provider='facebook',
                                       name='Facebook',
                                       client_id='Foo',
                                       secret='Bar'
                                       )
        app.sites.add(site)
        app.save()
        app = SocialApp.objects.create(provider='twitter',
                                       name='Twitter',
                                       client_id='Foo',
                                       secret='Bar'
                                       )
        app.sites.add(site)
        app.save()
        app = SocialApp.objects.create(provider='google',
                                       name='Google',
                                       client_id='Foo',
                                       secret='Bar'
                                       )
        app.sites.add(site)
        app.save()
    '''

    def handle(self, *args, **options):

        if Account.objects.count() == 0:
            # If there are no Accounts, we can assume this is a new Env
            # create a super user
            self._create_super_users()

            # Also fixup  the Site info
            self._fix_site_record()

            self._admin = Account.objects.first()

            # Create One Org for Arch
            org = _create_vendor_org(admin_user=self._admin)

            # Create a number of Physical Devices for testing purposes
            self._create_test_devices(org=org)

        else:
            print('Admin accounts can only be initialized if no Accounts exist')
            self._admin = Account.objects.first()

        if ProjectTemplate.objects.count() == 0:
            admin = Account.objects.first()
            org = Org.objects.filter(is_vendor=True).first()
            templates = _create_project_templates(admin_user=admin, org=org)

        '''
        if SocialApp.objects.count() == 0:
            if not getattr(settings, 'PRODUCTION'):
                self._create_social_accounts(site)
        '''
