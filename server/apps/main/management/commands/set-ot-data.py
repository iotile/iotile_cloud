import datetime
import json
import logging
import os

from django.core.management.base import BaseCommand
from django.template.defaultfilters import slugify

from apps.authentication.models import Account
from apps.orgtemplate.models import OrgTemplate

logger = logging.getLogger(__name__)


class Command(BaseCommand):

    def _get_data_file_path(self, filename):
        path = os.path.join(os.path.dirname(__file__), 'ot-data', filename)
        return path

    def parse_org_template(self, user):
        count = 0
        path = os.path.join(os.path.dirname(__file__), 'ot-data')
        for filename in os.listdir(path):
            with open(self._get_data_file_path(filename)) as infile:
                data = json.load(infile)
            if data:
                count += 1
                org = None
                if 'name' in data and 'minor_version' in data and 'major_version' in data and 'patch_version' in data:
                    expected_slug = slugify('{0}--v{1}-{2}-{3}'.format(data['name'],
                                                                       data['major_version'],
                                                                       data['minor_version'],
                                                                       data['patch_version']))
                    try:
                        ot = OrgTemplate.objects.get(slug=expected_slug)
                        logger.info('Update org template ' + ot.slug)
                    except OrgTemplate.DoesNotExist:
                        # create a new DeviceTemplate if not exist.
                        ot = OrgTemplate.objects.create_template(name=data['name'],
                                                                 major_version=data['major_version'],
                                                                 minor_version=data['minor_version'],
                                                                 patch_version=data['patch_version'],
                                                                 created_by=user)
                        logger.info('Create org template ' + ot.slug)
                    ot.extra_data = data['extra_data']
                    ot.save()
            else:
                logger.error('Data non valid.')
        #  return the number of device template json file (with data)
        return count

    def handle(self, *args, **options):
        admin = Account.objects.get_admin()
        total = self.parse_org_template(admin)
        if not total == OrgTemplate.objects.filter(active=True).count():
            logger.warning("The number of org template in database and in json files don't match ! "
                           "Found {0} in json file. Found {1} in database".format(
                total, OrgTemplate.objects.active_templates().count()))
        logger.info('Complete updating Org Templates')
