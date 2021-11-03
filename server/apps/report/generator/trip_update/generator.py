import csv
import logging
from io import StringIO

from iotile_cloud.utils.gid import IOTileDeviceSlug, IOTileProjectSlug, IOTileStreamSlug, IOTileVariableSlug

from apps.physicaldevice.models import Device
from apps.property.models import GenericProperty
from apps.utils.data_helpers.manager import DataManager
from apps.utils.gid.convert import gid2int
from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.timezone_utils import formated_timedelta

from ..base import ReportGenerator

_TRIP_SUMMARY_VID = gid2int(SYSTEM_VID['TRIP_SUMMARY'])
logger = logging.getLogger(__name__)


def dt_format(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S')


class TripUpdateReportGenerator(ReportGenerator):
    _device_slugs = None

    def __init__(self, msgs, rpt, start, end, sources=None):
        super(TripUpdateReportGenerator, self).__init__(msgs, rpt, start, end, sources)
        self._device_slugs = set()
        if sources:
            for source in sources:
                try:
                    device = Device.objects.get(slug=source)
                except Device.DoesNotExist:
                    print('No device found')
                    continue

                self._device_slugs.add(device.slug)

    def _email_template(self):
        return 'report/trip_update'

    def _get_update_event(self, device):
        stream_slug = device.get_stream_slug_for(SYSTEM_VID['TRIP_UPDATE'])

        events = DataManager.filter_qs('event', stream_slug=str(stream_slug))
        return events.last()

    def _get_device_properties(self, device):
        if device:
            return GenericProperty.objects.object_properties_qs(obj=device, is_system=False)
        return None

    def _post_process(self, event):
        if not event or not event.extra_data:
            return
        for key in event.extra_data.keys():
            if isinstance(event.extra_data[key], float):
                event.extra_data[key] = float('{0:.2f}'.format(event.extra_data[key]))
            if key in ['Below 17C', 'Above 30C']:
                # Special case to convert seconds to formatted delay
                event.extra_data[key] = formated_timedelta(total_seconds=event.extra_data[key])
        event.save()

    def _send_summary_email(self, event, device, sg_config):
        template = self._email_template()
        def_properties = []
        property_keys = []
        data_table = []
        attachment = None

        if not event or not event.extra_data:
            logger.warning('No event or event.extra_data: {}'.format(event))
            return

        if 'update_keys' in sg_config:
            def_properties = sg_config['update_keys']
        if 'property_keys' in sg_config:
            property_keys = sg_config['property_keys']

        if len(def_properties) == 0:
            data_table.append({
                'name': 'Error',
                'value': 'Bad SG configuration. Missing summary_keys'
            })

        property_table = [
            {
                'name': 'Device',
                'value': str(device.slug)
            },
            {
                'name': 'Model',
                'value': str(device.template)
            }
        ]
        property_map = {}

        property_qs = self._get_device_properties(device)
        if property_qs:
            for property in property_qs:
                property_map[property.name] = property.value

        for key in property_keys:
            if key in property_map:
                row = {
                    'name': key,
                    'value': property_map[key]
                }
                property_table.append(row)

        for key in def_properties:
            if key in event.extra_data:
                row = {
                    'name': key,
                    'value': event.extra_data[key]
                }
                data_table.append(row)

        # Create CSV to attach
        rows = property_table + [{'name': '', 'value': ''}] + data_table
        if len(rows):
            csvfile = StringIO()
            fieldnames = list(rows[0].keys())

            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

            attachment = {
                'filename': '{}.summary.csv'.format(str(device.slug)),
                'content': csvfile.getvalue(),
                'mimetype': 'text/csv'
            }

        ctx = {
            'device_url': device.get_webapp_url(),
            'property_table': property_table,
            'data_table': data_table,
            'user': str(self._rpt.created_by) if self._rpt else None
        }

        self._send_email(template, ctx, attachment)

    def add_streams_for_qs(self, qs):
        for stream in qs:
            stream_slug = IOTileStreamSlug(stream.slug)
            parts = stream_slug.get_parts()
            assert 'variable' in parts
            assert 'device' in parts
            assert 'project' in parts
            device_slug = parts['device']
            self._device_slugs.add(device_slug)

    def process_config(self):
        # No configuration available yet
        pass

    def generate_user_report(self):
        """
        Simple get latest Trip Update event (0x5a08) and forward as an email.
        Use Sensor Graph information to properly format email

        :return: Nothing
        """

        for device_slug in self._device_slugs:
            logger.info('Processing Trip Update for: {}'.format(device_slug))

            try:
                device = Device.objects.get(slug=device_slug)
            except Device.DoesNotExist:
                print('No device found')
                continue

            sg = device.sg
            sg_config = None
            if 'analysis' in sg.ui_extra and 'trip_summary' in sg.ui_extra['analysis']:
                sg_config = sg.ui_extra['analysis']['trip_summary']

            # Get event with Trip Update
            event = self._get_update_event(device)
            if event:
                # Post-process event if needed
                self._post_process(event)

                # Send email with summary
                self._send_summary_email(event, device, sg_config)
