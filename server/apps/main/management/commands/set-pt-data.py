import datetime
import json
import logging
import os

from django.core.management.base import BaseCommand
from django.template.defaultfilters import slugify

from apps.authentication.models import Account
from apps.org.models import Org
from apps.projecttemplate.models import ProjectTemplate

logger = logging.getLogger(__name__)


class Command(BaseCommand):

    def _get_data_file_path(self, filename):
        path = os.path.join(os.path.dirname(__file__), 'pt-data', filename)
        return path

    def parse_project_template(self, user):
        count = 0
        path = os.path.join(os.path.dirname(__file__), 'pt-data')
        for filename in os.listdir(path):
            with open(self._get_data_file_path(filename)) as infile:
                data = json.load(infile)
            if data:
                count += 1
                org = None
                if 'org' in data:
                    try:
                        org = Org.objects.get(slug=data['org'])
                    except Org.DoesNotExist:
                        logger.error('Organization slug ' + data['org'] + ' does not exist!')
                        break
                if 'name' in data and 'minor_version' in data and 'major_version' in data and 'patch_version' in data:
                    expected_slug = slugify('{0}--v{1}-{2}-{3}'.format(data['name'],
                                                                       data['major_version'],
                                                                       data['minor_version'],
                                                                       data['patch_version']))
                    try:
                        pt = ProjectTemplate.objects.get(slug=expected_slug)
                        pt.org = org
                        logger.info('Update project template ' + pt.slug)
                    except ProjectTemplate.DoesNotExist:
                        # create a new DeviceTemplate if not exist.
                        pt = ProjectTemplate.objects.create_template(name=data['name'],
                                                                     major_version=data['major_version'],
                                                                     minor_version=data['minor_version'],
                                                                     patch_version=data['patch_version'],
                                                                     org=org,
                                                                     created_by=user)
                        logger.info('Create project template ' + pt.slug)
                    pt.extra_data = data['extra_data']
                    pt.save()
            else:
                logger.error('Data non valid.')
        #  return the number of device template json file (with data)
        return count

    def handle(self, *args, **options):
        admin = Account.objects.get_admin()
        total = self.parse_project_template(admin)
        if not total == ProjectTemplate.objects.filter(active=True).count():
            logger.warning("The number of project template in database and in json files don't match ! "
                           "Found {0} in json file. Found {1} in database".format(
                total, ProjectTemplate.objects.active_templates().count()))
        logger.info('Complete updating Project Templates')
