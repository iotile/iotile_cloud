from django.db.models import Q

from apps.configattribute.models import ConfigAttribute
from apps.property.models import GenericProperty
from apps.utils.data_helpers.manager import DataManager
from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.timezone_utils import display_formatted_ts


class TripInfo(object):
    block = None
    data = {}
    slug = None
    last_update = None

    def __init__(self, block):
        self.block = block
        self.slug = block.slug
        self.data = {
            'summary': {},
            'properties': {}
        }
        self.last_update = None

    def add_property(self, key, value):
        self.data['properties'][key] = value

    def add_summary_event(self, event):
        if 'summary' in self.data:
            if self.last_update and self.last_update > event.timestamp:
                return

        self.data['summary'] = event.extra_data
        # Trip Summary should win over Trip Update
        self.last_update = event.timestamp

    def to_representation(self):
        data = {
            'slug': self.slug,
            'label': self.block.title,
            'summary_date': display_formatted_ts(self.last_update) if self.last_update else '',
            'data': self.data
        }
        return data


class TripOrgQualityReport(object):
    org = None
    results = {}
    config = {}

    def __init__(self, org):
        self.org = org
        self.results = {}
        self.config = self._get_config_attributes()

    def _get_config_attributes(self):
        config_name = ':report:trip_quality:config'
        attribute = ConfigAttribute.objects.get_attribute_by_priority(name=config_name, target_slug=self.org.obj_target_slug)
        if attribute:
            return attribute.data
        # Return empty if it does not exist
        return {
            'summary_keys': [
                "Device",
                "START (UTC)",
                "END (UTC)",
                "Duration (Days)",
                "Event Count",
                "First event at (UTC)",
                "Last event at (UTC)",
                "Max Humidity (% RH)",
                "Min Humidity (% RH)",
                "Median Humidity (% RH)",
                "Max Pressure (Mbar)",
                "Min Pressure (Mbar)",
                "Median Pressure (Mbar)",
                "Max Temp (C)",
                "Min Temp (C)",
                "Median Temp (C)",
                "Above 30C",
                "Below 17C",
                "Max Peak (G)",
                "TimeStamp(MaxPeak) (UTC)",
                "DeltaV at Max Peak (in/s)",
                "MaxDeltaV (in/s)",
                "TimeStamp(MaxDeltaV) (UTC)",
                "Peak at MaxDeltaV (G)"
            ],
            'property_keys': []
        }

    def analyze(self):
        """
        Get all archives for an organization and fill a TripInfo object for each with the following

        - Selected trip properties (based on project's configAttribute)
        - Last Update Event, if any
        - Last Trip Summary Event, if any

        :return: Nothing
        """

        blocks = self.org.data_blocks.all()
        for block in blocks:
            self.results[block.slug] = TripInfo(block)

        block_slugs = [block.slug for block in blocks]
        if self.config and 'property_keys' in self.config:
            for property_item in self.config['property_keys']:
                properties = GenericProperty.objects.filter(target__in=block_slugs, name=property_item)
                for p in properties:
                    self.results[p.target].add_property(property_item, p.value)

        # Not great, but we seem to have blocks with project as None and blocks as p--0000
        q = Q(project_slug='') | Q(project_slug='p--0000-0000')
        q = q & Q(device_slug__in=block_slugs, variable_slug__icontains=SYSTEM_VID['TRIP_SUMMARY'])
        events = DataManager.filter_qs_using_q(
            'event',
            q=q
        )
        for event in events:
            self.results[event.device_slug].add_summary_event(event)

        # Cleanup reports that don't look complete (No Summary or Properties)
        to_delete = []
        for slug, trip in self.results.items():
            if trip.data['summary'] == {}:
                # Delete Archive that does not represent a real trip
                to_delete.append(slug)
        for slug in to_delete:
            del(self.results[slug])
