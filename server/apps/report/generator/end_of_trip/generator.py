import csv
import datetime
import logging
import time
from io import StringIO

import numpy as np
import pandas as pd

from django.db.models import Q
from django.utils import timezone

from iotile_cloud.utils.gid import IOTileBlockSlug, IOTileDeviceSlug, IOTileStreamSlug, IOTileVariableSlug

from apps.physicaldevice.models import Device
from apps.property.models import GenericProperty
from apps.sqsworker.exceptions import WorkerActionHardError
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.utils import get_stream_output_mdo
from apps.utils.aws.redshift import get_ts_from_redshift
from apps.utils.data_helpers.manager import DataManager
from apps.utils.gid.convert import get_device_and_block_by_did, gid2int
from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.objects.utils import get_device_or_block
from apps.utils.timezone_utils import convert_to_utc, str_to_dt_utc

from ..base import ReportGenerator

_TRIP_SUMMARY_VID = gid2int(SYSTEM_VID['TRIP_SUMMARY'])
logger = logging.getLogger(__name__)


def dt_format(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S')


class TripSummary(object):
    """    Represents a Trip Summary
    """
    _lid_map = {
        '5020': 's_events',
        '5021': 's_pressure',
        '5022': 's_humidity',
        '5023': 's_temp',
        SYSTEM_VID['TRIP_SUMMARY']: 's_summary',  # Trip Report Summary
    }
    s_temp = None
    s_humidity = None
    s_pressure = None
    s_events = None
    s_start = None
    s_summary = None
    device_or_block_slug = ''
    # project_slug = ''
    ts_start = None
    ts_end = None
    data = None
    no_start_trip = False
    data_was_masked = False
    device_or_block = None

    def __init__(self, device_or_block):
        self.device_or_block = device_or_block
        try:
            self.device_or_block_slug = IOTileDeviceSlug(device_or_block.slug)
        except ValueError:
            self.device_or_block_slug = IOTileBlockSlug(device_or_block.slug)

        # self.project_slug = IOTileProjectSlug(p_slug)
        self.s_temp = None
        self.s_humidity = None
        self.s_pressure = None
        self.s_events = None
        self.s_start = None
        self.s_end = None
        self.s_summary = None
        self.ts_start = None
        self.ts_end = None
        self.data = None
        self.no_start_trip = False
        self.data_was_masked = False

    @classmethod
    def compute_time_active(cls, df, condition_met_count):
        """
        This hard-to-name function is used to take a dataframe, and a condition_met_count
        representing the number of rows that meet some condition (e.g. df['value'] < 17).sum())
        The function uses the first and last index to determine the time delta between
        and with it, the average time delta between values.
        It then computes the amount of time where the given condition was met.

        This is used to compute, for example, the amount of time that a POD was under 17C
        or above 30C

        :param df: DataFrame with a 'value' column and timestamp index
        :param condition_met_count: Number of rows that meet condition
        :return: string representation of the datetime.timedelta
        """
        first_value = df.iloc[0].name
        last_value = df.iloc[-1].name
        delta = last_value - first_value
        count = df['value'].count()

        if int(condition_met_count):
            time_in_condition = delta / int(count - 1) * int(condition_met_count)
            result = str(time_in_condition.to_pytimedelta())
        else:
            result = '0:00:00'

        return result

    def _get_stream_slug_for(self, variable):
        stream_slug = self.device_or_block.get_stream_slug_for(variable)
        return str(stream_slug)

    def _q_by_stream(self, stream_slug):
        """Create QuerySet filter with datetime ranges if available"""
        q = Q(stream_slug=stream_slug)
        if self.ts_start:
            q = q & Q(timestamp__gte=get_ts_from_redshift(self.ts_start))
        if self.ts_end:
            q = q & Q(timestamp__lte=get_ts_from_redshift(self.ts_end))

        logger.info('--> {}'.format(q))

        return q

    def add_stream(self, lid, stream):
        if lid in self._lid_map:
            self.__setattr__(self._lid_map[lid], stream)

    def _get_time_dataframe(self, stream):
        qs = DataManager.df_filter_qs_using_q('data', self._q_by_stream(stream.slug))
        df = qs.to_dataframe(['value', ], index='timestamp')
        mdo = get_stream_output_mdo(stream)
        if mdo:
            try:
                df['value'] = df['value'].apply(lambda x: mdo.compute(x))
            except Exception as e:
                raise WorkerActionHardError(e)

        return df

    def _compute_basic_env_stats(self, name, df, units):
        stats = df.agg(['min', 'median', 'max'])
        if not stats.empty:
            return {
                'Max {} ({})'.format(name, units): stats.loc['max'].values[0],
                'Min {} ({})'.format(name, units): stats.loc['min'].values[0],
                'Median {} ({})'.format(name, units): stats.loc['median'].values[0],
            }
        return {}

    def _compute_delta_v(self, x):
        terms = [x[term] for term in self._delta_v_terms]
        max_dv = max(*terms)
        min_dv = min(*terms)
        if max_dv > abs(min_dv):
            return max_dv
        return min_dv

    def _compute_event_data(self, event_qs, sg_config_consts):

        dt_index = pd.to_datetime([x.timestamp for x in event_qs])
        extra_data = [x.extra_data for x in event_qs]

        assert 'max_g_col' in sg_config_consts
        assert 'max_dv_col' in sg_config_consts
        max_g_col = sg_config_consts['max_g_col']
        max_dv_col = sg_config_consts['max_dv_col']

        df = pd.DataFrame(extra_data, index=dt_index)

        # For Saver backwards compatibility, look for alternative labels
        if max_g_col not in list(df):
            max_g_col = 'max_peak'
            if 'max_g' not in list(df):
                data = {
                    'Max Peak (G)': 'Error: peak or max_g not found'
                }
                return data

        data = {
            'First event at (UTC)': dt_format(df.iloc[0].name),
            'Last event at (UTC)': dt_format(df.iloc[-1].name),
            'Event Count': int(df[max_g_col].count())
        }
        if self.no_start_trip:
            # For backwards compatibility, if there was no start trip, use first/last event for duration
            data['Duration (Days)'] = (df.iloc[-1].name - df.iloc[0].name) / datetime.timedelta(days=1)

        if max_g_col in list(df):
            max_g_idx = df[max_g_col].idxmax()
            if 'delta_v_terms' in sg_config_consts:
                for col in sg_config_consts['delta_v_terms']:
                    if col in list(df):
                        df[col] = df[col].apply(lambda x: x * sg_config_consts['delta_v_multiplier'])

            if max_dv_col not in list(df):
                self._delta_v_terms = sg_config_consts['delta_v_terms']
                df[max_dv_col] = df.apply(self._compute_delta_v, axis=1)
            max_dv_idx = df[max_dv_col].idxmax()

            data.update({
                'TimeStamp(MaxPeak) (UTC)': dt_format(max_g_idx),
                'Max Peak (G)': df[max_g_col].loc[max_g_idx].max(),
                'DeltaV at Max Peak (in/s)': df[max_dv_col].loc[max_g_idx].max(),
                'TimeStamp(MaxDeltaV) (UTC)': dt_format(max_dv_idx),
                'MaxDeltaV (in/s)': df[max_dv_col].loc[max_dv_idx].max(),
                'Peak at MaxDeltaV (G)': df[max_g_col].loc[max_dv_idx].max(),
            })

        return data

    def _get_mask_event(self):
        """
        :return: Dict object if a mask has been set:
                 {'start': '<datetime_str>', 'end': '<datetime_str>'}.
                 None if not set
        """
        mask_stream_slug = self._get_stream_slug_for(SYSTEM_VID['DEVICE_DATA_MASK'])
        if mask_stream_slug:
            event = DataManager.filter_qs('event', stream_slug=mask_stream_slug).last()
            if event:
                assert ('start' in event.extra_data)
                assert ('end' in event.extra_data)
                return event.extra_data
        return None

    def calculate_trip_date_ranges(self):
        """
        Figure out the trip Start and End times:

        1. Check for TripStart and Trip End
        2. Check if TripMask is set. If so, use that (if within trip start/end

        :return: Nothing
        """
        start_trip_stream_slug = self._get_stream_slug_for(SYSTEM_VID['TRIP_START'])
        end_trip_stream_slug = self._get_stream_slug_for(SYSTEM_VID['TRIP_END'])

        qs = DataManager.filter_qs(
            'data',
            stream_slug__in=[start_trip_stream_slug, end_trip_stream_slug]
        ).order_by('streamer_local_id', 'timestamp')

        self.ts_start = self.ts_end = None
        for d in qs:
            if d.stream_slug == start_trip_stream_slug:
                self.ts_start = convert_to_utc(d.timestamp)
            if d.stream_slug == end_trip_stream_slug:
                self.ts_end = convert_to_utc(d.timestamp)

        # Check if the device has a data mask. If so, use instead
        mask_data = self._get_mask_event()
        if mask_data:
            if mask_data['start']:
                self.ts_start = str_to_dt_utc(mask_data['start'])
            self.data_was_masked = True
            if mask_data['end']:
                self.ts_end = str_to_dt_utc(mask_data['end'])
                self.data_was_masked = True

        if not self.ts_start:
            logger.info('No TripStart data found. Looking for oldest data')
            # For backwards compatibility, if no TRIP_START, look for the oldest Event or Data
            first_event = DataManager.filter_qs_using_q(
                'event',
                self._q_by_stream(self.s_events.slug)
            ).exclude(extra_data__has_key='error').first()
            first_temp = DataManager.filter_qs_using_q(
                'data',
                self._q_by_stream(self.s_temp.slug)
            ).first()

            if first_event and first_temp:
                first = first_temp if convert_to_utc(first_temp.timestamp) < convert_to_utc(first_event.timestamp) else first_event
            else:
                first = first_temp or first_event

            if first:
                self.ts_start = convert_to_utc(first.timestamp)
                self.no_start_trip = True
            else:
                logger.warning('No TRIP_START or events found')
                return

        if self.ts_end and self.ts_end < self.ts_start:
            # This is the end of a previous trip. Ignore
            self.ts_end = None

        logger.info('Trip Date Range: {} to {}'.format(
            self.ts_start,
            self.ts_end if self.ts_end else 'NOW'
        ))

    def _send_debug_info(self):
        # Print debug information
        msg = 'No Events Found: {}'.format(self.device_or_block_slug)

        q = self._q_by_stream(self.s_events.slug)
        msg += '\n --> q= {}'.format(str(q))

        event_qs = DataManager.filter_qs_using_q(
            'event',
            self._q_by_stream(self.s_events.slug)
        ).exclude(extra_data__has_key='error')
        msg += '\n--> events.filter(q): {}'.format(event_qs.count())

        q = Q(stream_slug=self.s_events.slug)
        event_qs = DataManager.filter_qs_using_q(
            'event',
            q
        )
        msg += '\n--> events.filter(slug): {}'.format(event_qs.count())

        if self.ts_start:
            msg += '\n--> start (UTC): {}'.format(convert_to_utc(self.ts_start))
        else:
            msg += '\n--> start  (UTC): Not Available'
        if self.ts_end:
            msg += '\n--> end  (UTC): {}'.format(convert_to_utc(self.ts_end))
        else:
            msg += '\n--> end  (UTC): Not Available'

        logger.info(msg)

        # Let customer know

    def calculate_trip_summary_data(self, sg_config):

        data = {
            'Device': str(self.device_or_block_slug),
        }

        if self.s_events:
            q = self._q_by_stream(self.s_events.slug)
            logger.info('_q_by_stream({}) = {}'.format(self.s_events.slug, q))

            event_qs = DataManager.filter_qs_using_q(
                'event',
                self._q_by_stream(self.s_events.slug)
            ).exclude(extra_data__has_key='error')
            logger.info('--> Trip {} events: {}'.format(self.device_or_block_slug, event_qs.count()))
        else:
            event_qs = DataManager.none_qs('event')
            data['error'] = 'Error: s_events is None'
            logger.warning(data['error'])

        if self.ts_start and not self.no_start_trip:
            data['START (UTC)'] = dt_format(self.ts_start)
            if self.ts_end:
                data['END (UTC)'] = dt_format(self.ts_end)
                data['Duration (Days)'] = (self.ts_end - self.ts_start) / datetime.timedelta(days=1)
        else:
            data['START (UTC)'] = 'Not Available'
            data['END (UTC)'] = 'Not Available'

        assert 'START (UTC)' in data

        if self.data_was_masked:
            data['Notes'] = 'Trip Start and/or End was overwritten by a set device data mask'

        if event_qs.count():
            if 'consts' in sg_config:
                sg_config_consts = sg_config['consts']

                data.update(self._compute_event_data(event_qs, sg_config_consts))
        else:
            logger.warning('No events found')
            data['Max Peak (G)'] = 'Error: No events found'
            data['Event Count'] = 0

            self._send_debug_info()

        if self.s_temp:
            df = self._get_time_dataframe(self.s_temp)
            if not df.empty:
                # Compute time delta so we can show how much time the device was
                # above or below the required range
                data.update(self._compute_basic_env_stats('Temp', df, 'C'))
                data['Below 17C'] = TripSummary.compute_time_active(df=df, condition_met_count=(df['value'] < 17).sum())
                data['Above 30C'] = TripSummary.compute_time_active(df=df, condition_met_count=(df['value'] > 30).sum())
            else:
                logger.warning('No Temp stream found')

        if self.s_humidity:
            df = self._get_time_dataframe(self.s_humidity)
            if not df.empty:
                data.update(self._compute_basic_env_stats('Humidity', df, '% RH'))
            else:
                logger.warning('No Humidity stream found')

        if self.s_pressure:
            df = self._get_time_dataframe(self.s_pressure)
            if not df.empty:
                data.update(self._compute_basic_env_stats('Pressure', df, 'Mbar'))
        else:
            logger.warning('No Pressure stream found')

        self.data = data


class EndOfTripReportGenerator(ReportGenerator):
    _trips = {}

    def __init__(self, msgs, rpt, start, end, sources=None):
        super(EndOfTripReportGenerator, self).__init__(msgs, rpt, start, end, sources)
        self._trips = {}
        if sources:
            for source in sources:
                obj = get_device_or_block(source)
                if not obj:
                    continue

                logger.info('creating new TripSummary for device {}'.format(obj.slug))
                self._trips[obj.slug] = TripSummary(obj)

    def _email_template(self):
        return 'report/end_of_trip'

    def _create_summary_event(self, trip):
        if not trip.s_summary:
            # Need to create Summary Stream
            if isinstance(trip.device_or_block, Device):
                device = trip.device_or_block
                project = device.project
                block = None
            else:
                block = trip.device_or_block
                device = trip.device_or_block.device
                project=None

            trip.s_summary = StreamId.objects.create_stream(
                project=project,
                device=device,
                block=block,
                variable=None,
                data_type='E0',
                var_lid=_TRIP_SUMMARY_VID,
                var_name='Trip Summary',
                created_by=device.claimed_by,
                data_label='Trip Summary: {}'.format(trip.device_or_block_slug)
            )

        summary = DataManager.build(
            'event',
            stream_slug=trip.s_summary.slug,
            timestamp=timezone.now(),
            device_timestamp=int(time.time()),
            streamer_local_id=1,
            extras={
                'extra_data': trip.data,
            },
        )
        summary.deduce_slugs_from_stream_id()
        try:
            logger.info('Uploading Trip Summary: {}'.format(trip.s_summary.slug))
            DataManager.save('event', summary)
        except Exception as e:
            WorkerActionHardError(e)

    def _get_obj_properties(self, device_or_block):
        if device_or_block:
            return GenericProperty.objects.object_properties_qs(obj=device_or_block, is_system=False)
        return None

    def _send_summary_email(self, trip, device_or_block, sg_config):
        template = self._email_template()
        def_properties = []
        property_keys = []
        data_table = []
        attachment = None

        if 'summary_keys' in sg_config:
            def_properties = sg_config['summary_keys']
        if 'property_keys' in sg_config:
            property_keys = sg_config['property_keys']

        if len(def_properties) == 0:
            data_table.append({
                'name': 'Error',
                'value': 'Bad SG configuration. Missing summary_keys'
            })

        try:
            device_model = str(device_or_block.template)
        except Exception:
            device_model = 'Unk'

        property_table = [
            {
                'name': 'Device',
                'value': str(trip.device_or_block_slug)
            },
            {
                'name': 'Model',
                'value': device_model
            }
        ]
        property_map = {}

        property_qs = self._get_obj_properties(device_or_block)
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
            if key in trip.data:
                row = {
                    'name': key,
                    'value': trip.data[key]
                }
                if isinstance(trip.data[key], np.float64) or isinstance(trip.data[key], float):
                    row['value'] = '{0:.2f}'.format(trip.data[key])
                data_table.append(row)

        if 'Notes' in trip.data:
            row = {
                'name': 'Notes',
                'value': trip.data['Notes']
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
                'filename': '{}.summary.csv'.format(str(trip.device_or_block_slug)),
                'content': csvfile.getvalue(),
                'mimetype': 'text/csv'
            }

        ctx = {
            'device_url': device_or_block.get_webapp_url(),
            'property_table': property_table,
            'data_table': data_table,
            'user': str(self._rpt.created_by) if self._rpt else None,
            'org': str(self._rpt.org) if self._rpt else None
        }

        self._send_email(template, ctx, attachment)

    def add_streams_for_qs(self, qs):
        for stream in qs:
            stream_slug = IOTileStreamSlug(stream.slug)
            parts = stream_slug.get_parts()
            assert 'variable' in parts
            assert 'device' in parts
            assert 'project' in parts
            variable = IOTileVariableSlug(parts['variable'])
            lid = variable.formatted_local_id()
            device_or_block_slug = parts['device']
            # TODO: Fix correctly
            # HACK: Try to recover data block
            block_id, device_id = get_device_and_block_by_did(device_or_block_slug)
            if block_id > 0:
                # This is a block
                device_gid = device_or_block_slug.split('--')[1]
                device_or_block_slug = '--'.join(['b', device_gid])
            if device_or_block_slug not in self._trips:
                logger.info('creating new TripSummary for device {}'.format(device_or_block_slug))
                device_or_block = get_device_or_block(device_or_block_slug)
                if not device_or_block:
                    continue
                self._trips[device_or_block_slug] = TripSummary(device_or_block)

            logger.info('Adding stream {} ({}) for trip summary for {}'.format(stream, lid, device_or_block_slug))
            self._trips[device_or_block_slug].add_stream(lid, stream)

    def process_config(self):
        # No configuration available yet
        pass

    def generate_user_report(self):
        """
        Generate an End of Trip Summary Report

        :return: Nothing
        """

        for slug in self._trips.keys():

            trip = self._trips[slug]
            device_or_block = trip.device_or_block

            sg = device_or_block.sg
            if 'analysis' in sg.ui_extra and 'trip_summary' in sg.ui_extra['analysis']:
                sg_config = sg.ui_extra['analysis']['trip_summary']
            else:
                sg_config = {}

            if not trip.s_events:
                # We have no Events. It is possible the database is not up to date
                # Reschedule to try again later
                if self.reschedule_callback:
                    logger.warning('No events. Rescheduling')
                    self.reschedule_callback(900)

            trip.calculate_trip_date_ranges()

            if trip.ts_start:
                # If no start date, there is no data to compute
                trip.calculate_trip_summary_data(sg_config)

                if trip.data:

                    # Create a TRIP_SUMMARY StreamEventData record
                    self._create_summary_event(trip)

                    # Send email with summary
                    self._send_summary_email(trip, device_or_block, sg_config)

            else:
                logger.info('Cannot create Trip Summary Report: No START signal found')
