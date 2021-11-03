
from iotile_cloud.utils.gid import IOTileDeviceSlug, IOTileProjectSlug, IOTileStreamSlug, IOTileVariableSlug

from apps.configattribute.models import ConfigAttribute
from apps.property.models import GenericProperty
from apps.utils.data_helpers.manager import DataManager
from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.timezone_utils import display_formatted_ts


class TripInfo(object):
    device = None
    data = {}
    slug = None
    state_label = None
    state_id = None
    last_update = None
    trip_end_ts = None
    last_mid_trip_ts = None
    property = {}

    def __init__(self, device):
        self.device = device
        self.slug = device.slug
        self.state_label = device.get_state_display()
        self.state_id = device.state
        self.data = {}
        self.last_update = None
        self.trip_ended = None
        self.last_mid_trip_ts = None
        self.property = {}

    def get_last_update_display(self):
        if self.last_update:
            return display_formatted_ts(self.last_update)
        return ''

    def is_active(self):
        return self.state_id == 'N1'

    def update_type(self):
        if 'summary' in self.data:
            return 'S'
        if 'update' in self.data:
            return 'U'
        return ''

    def add_property(self, key, value):
        self.property[key] = value

    def set_trip_end(self, data):
        self.trip_end_ts = data.timestamp

    def set_mid_trip(self, data):
        if self.last_mid_trip_ts is None:
            self.last_mid_trip_ts = data.timestamp
        else:
            if data.timestamp > self.last_mid_trip_ts:
                self.last_mid_trip_ts = data.timestamp

    def add_update_event(self, event):
        if 'update' in self.data:
            if self.last_update and self.last_update > event.timestamp:
                return 0

        self.state_label = 'Normal - Active (Update)'
        self.data['update'] = event.extra_data
        self.last_update = event.timestamp
        return 1

    def add_summary_event(self, event):
        if 'summary' in self.data:
            if self.last_update and self.last_update > event.timestamp:
                return 0

        if self.trip_end_ts is None and self.last_mid_trip_ts is not None:
            # Assume if it is a mid-trip report if there is a mid trip report
            # and the trip has not ended
            # Assuming we cannot have mid-trip after the trip ended
            self.state_label = 'Normal - Active (Update)'
            self.data['update'] = event.extra_data
        else:
            # For backwards compatibility (including savers)
            # don't check for trip_end_ts as savers won't produce it
            self.state_label = 'Normal - Trip Ended'
            self.data['summary'] = event.extra_data

        # Trip Summary should win over Trip Update
        self.last_update = event.timestamp
        return 1

    def to_representation(self):
        data = {
            'slug': self.slug,
            'label': self.device.label,
            'state_label': self.state_label,
            'state_id': self.state_id,
            'last_update': display_formatted_ts(self.last_update) if self.last_update else '',
            'properties': self.property
        }
        if self.device.external_id:
            data['external_id'] = self.device.external_id
        return data


class TripProjectStatusReport(object):
    project = None
    results = {}
    config = {}
    device_count = 0
    active_count = 0
    ended_count = 0

    def __init__(self, project):
        self.project = project
        self.results = {}
        self.config = self._get_config_attributes()
        self.device_count = 0
        self.active_count = 0
        self.ended_count = 0

    def _get_variable_slug(self, lid):
        project_slug = IOTileProjectSlug(self.project.slug)
        return IOTileVariableSlug(lid, project=project_slug)

    def _get_config_attributes(self):
        config_name = ':report:trip_status:config'
        attribute = ConfigAttribute.objects.get_attribute_by_priority(name=config_name, target_slug=self.project.slug)
        if attribute:
            return attribute.data
        # Get defaults
        return {
            "properties": [
                {"label": "Ship From", "key": "from"},
                {"label": "Ship To", "key": "to"}
            ],
            "show_external_id": False
        }

    def analyze(self):
        """
        Get all devices for a project and fill a TripInfo object for each with the following

        - Selected trip properties (based on project's configAttribute)
        - Last Update Event, if any
        - Last Trip Summary Event, if any

        :return: Nothing
        """

        devices = self.project.devices.all()
        self.device_count = devices.count()
        self.active_count = 0
        for device in devices:
            self.results[device.slug] = TripInfo(device)
            if self.results[device.slug].is_active():
                self.active_count += 1

        device_slugs = [device.slug for device in devices]
        if self.config and 'properties' in self.config:
            for property_item in self.config['properties']:
                properties = GenericProperty.objects.filter(target__in=device_slugs, name=property_item['label'])
                for p in properties:
                    self.results[p.target].add_property(property_item['key'], p.value)

        trip_end_data = DataManager.filter_qs(
            'data',
            project_slug=self.project.slug,
            device_slug__in=device_slugs,
            variable_slug=self._get_variable_slug(SYSTEM_VID['TRIP_END'])
        )
        for data in trip_end_data:
            self.results[data.device_slug].set_trip_end(data)

        mid_trip_report = DataManager.filter_qs(
            'data',
            project_slug=self.project.slug,
            device_slug__in=device_slugs,
            variable_slug=self._get_variable_slug(SYSTEM_VID['MID_TRIP_DATA_UPLOAD'])
        )
        for data in mid_trip_report:
            self.results[data.device_slug].set_mid_trip(data)

        events = DataManager.filter_qs(
            'event',
            project_slug=self.project.slug,
            device_slug__in=device_slugs,
            variable_slug=self._get_variable_slug(SYSTEM_VID['TRIP_UPDATE'])
        )
        for event in events:
            self.results[event.device_slug].add_update_event(event)

        events = DataManager.filter_qs(
            'event',
            project_slug=self.project.slug,
            device_slug__in=device_slugs,
            variable_slug=self._get_variable_slug(SYSTEM_VID['TRIP_SUMMARY'])
        )
        self.ended_count = 0
        for event in events:
            self.ended_count += self.results[event.device_slug].add_summary_event(event)
