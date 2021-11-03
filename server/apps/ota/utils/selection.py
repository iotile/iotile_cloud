from django.db.models import Q

from apps.physicaldevice.models import Device
from apps.org.models import Org
from apps.devicetemplate.models import DeviceTemplate
from ..models import DeploymentRequest, DeviceVersionAttribute


op_by_type = {
    'os_tag': ['eq'],
    'os_version': ['lte', 'eq', 'lt', 'gt', 'gte'],
    'app_tag': ['eq'],
    'app_version': ['lte', 'eq', 'lt', 'gt', 'gte'],
    'controller_hw_tag': ['eq']
}


def validate_value_by_type(input_type, input_value):
    if '_tag' in input_type:
        try:
            int(input_value)
        except ValueError:
            return False

    if '_version' in input_type:
        # Semantic versioning says "major.minor.patch", but patch is optional
        content = input_value.split('.')
        if len(content) < 2 or len(content) > 4:
            return False
        return True

    return True


class DeviceSelectionRule(object):
    type = ''
    op = ''
    value = ''

    def __init__(self, rule_str):
        parts = rule_str.split(':')
        assert len(parts) == 3
        self.type = parts[0]
        self.op = parts[1]
        self.value = parts[2]

    def __str__(self):
        return ':'.join([self.type, self.op, self.value])

    def _version_tag_type(self):
        parts = self.type.split('_')
        assert len(parts) == 2
        factory = {
            'os': 'os',
            'app': 'sg'
        }
        if parts[0] in factory:
            return factory[parts[0]]
        return ''

    def q(self):
        if self.type in ['os_tag', 'app_tag']:
            return Q(tag=self.value, type=self._version_tag_type())
        if self.type in ['os_version', 'app_version']:
            version_parts = self.value.split('.')
            major = int(version_parts[0])
            minor = 0
            if len(version_parts) >= 2:
                minor = int(version_parts[1])
            version_factory = {
                'eq': Q(major_version=major, minor_version=minor, type=self._version_tag_type()),
                'lt': Q(major_version=major, minor_version__lt=minor, type=self._version_tag_type()) |
                      Q(major_version__lt=major, type=self._version_tag_type()),
                'lte': Q(major_version=major, minor_version__lte=minor, type=self._version_tag_type()) |
                       Q(major_version__lt=major, type=self._version_tag_type()),
                'gt': Q(major_version=major, minor_version__gt=minor, type=self._version_tag_type()) |
                      Q(major_version__gt=major, type=self._version_tag_type()),
                'gte': Q(major_version=major, minor_version__gte=minor, type=self._version_tag_type()) |
                       Q(major_version__gt=major, type=self._version_tag_type()),
            }
            if self.op in version_factory.keys():
                return version_factory[self.op]
        return None


class DeploymentDeviceSelectionHelper(object):
    _deployment_request = None
    _rules = []

    def __init__(self, dr):
        self._deployment_request = dr
        self._rules = []
        self._parse_selection_criteria()

    def _parse_selection_criteria(self):
        for criteria in self._deployment_request.selection_criteria:
            self._rules.append(DeviceSelectionRule(criteria))

    def _base_device_qs(self):
        """
        First level of filtering based on type of Deployment:
        - Global Vendor deployment returns all active and claimed devices sold by them
        - Org Deployment returns Org Devices
        - Fleet FDeployment returns Fleet Devices
        :return: Device QuerySet
        """
        if self._deployment_request.fleet:
            fleet_device_qs = self._deployment_request.fleet.members.all()
            return fleet_device_qs

        if self._deployment_request.org.is_vendor:
            vendor_templates = DeviceTemplate.objects.filter(org=self._deployment_request.org)
            return Device.objects.filter(template__in=vendor_templates, active=True, project__isnull=False)

        q = Q(org=self._deployment_request.org)
        return Device.objects.filter(q)

    def _filter_by_criteria(self, qs):
        version_q = Q(device__in=qs)
        for rule in self._rules:
            rule_q = rule.q()
            if rule_q:
                # If rule is legal
                version_q = version_q & rule_q

        device_ids = [v['device'] for v in DeviceVersionAttribute.objects.filter(version_q).values('device')]
        return qs.filter(id__in=device_ids)

    def affected_devices_qs(self):
        qs = self._base_device_qs()
        qs = self._filter_by_criteria(qs)
        return qs
