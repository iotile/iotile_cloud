import datetime
import json
import logging
import os
import sys

from django.core.management.base import BaseCommand
from django.template.defaultfilters import slugify
from django.utils import timezone

from apps.authentication.models import Account
from apps.component.models import Component
from apps.devicetemplate.models import DeviceSlot, DeviceTemplate
from apps.org.models import Org

logger = logging.getLogger(__name__)


def _get_data_dir_path(dirname):
    path = os.path.join(os.path.dirname(__file__), dirname)
    return path


class ComponentInfo(object):
    external_sku = ''
    internal_sku = ''
    slug = ''
    org = ""
    type = ''
    version = ''
    hw_tag = ''
    hw_name = ''
    description = ''
    active = True
    slot = None

    def __init__(self, data, physical_parent):
        if 'external_sku' in data:
            self.external_sku = data['external_sku']
        if 'type' in data:
            self.type = data['type']
        if 'org' in data:
            self.org = data['org']
        if 'slot' in data:
            self.slot = data['slot']
        if 'version' in data:
            self.version = data['version']
        if 'hw_tag' in data:
            self.hw_tag = data['hw_tag']
        if 'hw_name' in data:
            self.hw_name = data['hw_name']
        if 'description' in data:
            self.description = data['description']
        if 'active' in data:
            self.active = data['active']
        if 'slug' in data:
            self.slug = data['slug']
        else:
            self.slug = slugify('{0}-{1}'.format(self.external_sku, self.version))

    def create_record(self, user):
        ver = self.version.split('-')
        comp = Component.objects.create(external_sku=self.external_sku,
                                        internal_sku=self.internal_sku,
                                        active=self.active,
                                        org=self.org,
                                        type=self.type,
                                        hw_tag=self.hw_tag,
                                        hw_name=self.hw_name,
                                        description=self.description,
                                        major_version=int(ver[0]),
                                        minor_version=int(ver[1]),
                                        patch_version=int(ver[2]),
                                        created_by=user)
        return comp

    def update_record(self, comp):
        comp.type = self.type
        comp.active = self.active
        comp.hw_tag = self.hw_tag
        comp.hw_name = self.hw_name
        comp.internal_sku = self.internal_sku
        comp.description = self.description
        comp.save()
        return comp


class DeviceInfo(object):
    external_sku = ''
    internal_sku = ''
    family = ""
    org = ""
    os_tag = 0
    os_version_major = 0
    os_version_minor = 0
    hw_tag = 0
    hw_version_major = 0
    version = '0-0-0'
    description = ''
    components = []
    slug = ""
    active = True

    def __init__(self, data):
        self.os_tag = 0
        self.os_major_version = 0
        self.os_minor_version = 0
        self.hw_tag = 0
        self.hw_major_version = 0
        self.version = '0-0-0'

        if 'external_sku' in data:
            self.external_sku = data['external_sku']
        if 'internal_sku' in data:
            self.internal_sku = data['internal_sku']
        if 'os_tag' in data:
            self.os_tag = data['os_tag']
        if 'os_version' in data:
            os_ver = data['os_version'].split('.')
            if len(os_ver) > 0:
                self.os_major_version = int(os_ver[0])
            if len(os_ver) > 1:
                self.os_minor_version = int(os_ver[1])
        if 'hw_tag' in data:
            self.hw_tag = data['hw_tag']
        if 'hw_version' in data:
            self.hw_major_version = int(data['hw_version'])
        if 'family' in data:
            self.family = data['family']
        if 'org' in data:
            self.org = data['org']
        if 'version' in data:
            self.version = data['version']
        if 'active' in data:
            self.active = data['active']
        if 'description' in data:
            self.description = data['description']
        if 'components' in data:
            self.components = data['components']
        self.slug = slugify('{0}--v{1}'.format(self.external_sku, self.version))
    # return list of components in slots

    def create_record(self, user):
        ver = self.version.split('-')
        dt = DeviceTemplate.objects.create_template(external_sku=self.external_sku,
                                                    internal_sku=self.internal_sku,
                                                    active=self.active,
                                                    os_tag=self.os_tag,
                                                    os_major_version= self.os_major_version,
                                                    os_minor_version= self.os_minor_version,
                                                    hw_tag=self.hw_tag,
                                                    hw_major_version=self.hw_version_major,
                                                    family=self.family,
                                                    major_version=int(ver[0]),
                                                    minor_version=int(ver[1]),
                                                    patch_version=int(ver[2]),
                                                    description=self.description,
                                                    org=self.org,
                                                    released_on=timezone.now(),
                                                    created_by=user)
        return dt

    def update_record(self, dt):
        dt.os_tag = self.os_tag
        dt.active = self.active
        dt.internal_sku = self.internal_sku
        dt.family = self.family
        dt.org = self.org
        dt.description = self.description
        dt.os_major_version = self.os_major_version
        dt.os_minor_version = self.os_minor_version
        dt.hw_tag = self.hw_tag
        dt.hw_major_version = self.hw_major_version
        dt.save()
        return dt

    def get_slots(self):
        slots = []
        for c1 in self.components:
            comp = ComponentInfo(c1, "")
            if 'slot' in c1 and c1['slot'] is not None:
                slots += [comp]
            if 'merged' in c1 and c1['merged']:
                for c2 in c1['merged']:
                    if c2['slot'] is not None:
                        slots += [ComponentInfo(c2, comp.slug)]
        # data in json
        return slots


class DeviceData(object):
    devices = {}
    components = {}

    # load components from a list of components whose parent is physical_parent
    def load_component(self, list_data):
        for comp_data in list_data:
            c = ComponentInfo(comp_data, '')
            if c.slug not in self.components:
                self.components[c.slug] = c

    def load_device(self, list_data):
        for device_data in list_data:
            d = DeviceInfo(device_data)
            if d.slug not in self.devices:
                self.devices[d.slug] = d
            else:
                # should give a warning if different
                self.devices[d.slug].family = d.family
                self.devices[d.slug].org = d.org
                self.devices[d.slug].components = d.components

    def load_from_dir(self, dir_path):
        for filename in os.listdir(dir_path):
            with open(os.path.join(dir_path, filename)) as infile:
                data = json.load(infile)
            if data:
                if 'components' in data:
                    self.load_component(data['components'])
                if 'devices' in data:
                    self.load_device(data['devices'])


class Command(BaseCommand):

    def update_components(self, user, components):
        #  find a way to create non virtual first
        for slug, c in components.items():
            try:
                c.org = Org.objects.get(slug=c.org)
            except Org.DoesNotExist:
                logger.error('Organization slug' + c.org + ' does not exist!')
                break
            try:
                # update
                comp = Component.objects.get(slug=c.slug)
                comp = c.update_record(comp=comp)
                logger.info('Update component ' + comp.slug)
            except Component.DoesNotExist:
                # create a new Component if not exist.
                comp = c.create_record(user=user)
                logger.info('Create component ' + comp.slug)

    def update_device_template(self, user, devices):
        for slug, d in devices.items():
            try:
                d.org = Org.objects.get(slug=d.org)
            except Org.DoesNotExist:
                logger.error('Organization slug ' + d.org + ' does not exist!')
                break
            try:
                dt = DeviceTemplate.objects.get(slug=d.slug)
                dt = d.update_record(dt)
                logger.info('Update device template ' + dt.slug)
            except DeviceTemplate.DoesNotExist:
                # create a new DeviceTemplate if not exist.
                dt = d.create_record(user)
                logger.info('Create device template ' + dt.slug)
            self.create_update_slots(d.get_slots(), dt)
            dt.save()

    def create_update_slots(self, slots, dt):
        slots_json = []
        for s in slots:
            try:
                comp = Component.objects.get(slug=s.slug)
            except Component.DoesNotExist:
                logger.error('Component slug ' + s.slug + 'does not exist!')
                break
            try:
                ds = DeviceSlot.objects.get(template=dt,
                                            component=comp,
                                            number=s.slot)
            except DeviceSlot.DoesNotExist:
                ds = DeviceSlot.objects.create(template=dt,
                                               component=comp,
                                               number=s.slot)
            slots_json += [s.slot]

        # Give warning if database has additional data
        slots_database = DeviceSlot.objects.filter(template=dt)
        if len(slots_database) != len(slots_json):
            for i in slots_database:
                if i.number not in slots_json:
                    logger.warning('Found record not in json file: DeviceSlot number - {}'.format(i.number))
                    # DeviceSlot.objects.filter(id=i.id, template=dt).delete()

    def handle(self, *args, **options):
        admin = Account.objects.get_admin()
        data = DeviceData()
        data.load_from_dir(_get_data_dir_path('product-data'))
        self.update_components(admin, data.components)
        self.update_device_template(admin, data.devices)
        if not len(data.devices) == DeviceTemplate.objects.filter(active=True).count():
            logger.warning("The number of device template in database and in json files don't match ! "
                           "Found {0} in json file. Found {1} in database".format(len(data.devices),
                                                                                  DeviceTemplate.objects.filter(
                                                                                      active=True).count()))
        if not len(data.components) == Component.objects.all().count():
            logger.warning("The number of device template in database and in json files don't match ! "
                           "Found {0} in json file. Found {1} in database".format(len(data.components),
                                                                                  Component.objects.all().count()))
        logger.info('Complete updating device template')

'''
The import script handle duplicate declarations.
If a component doesn't have merged component, put "merged: null"
If a component doesn't have a slot number, put "slot: null"
Devices should be declared under "devices" (as a list) and components should be declared under "components" (as a list)
Version = major_version-minor_version-patch_version
'''