from pprint import pprint
from django.db.models import Sum, Max, Min

from apps.utils.mdo.helpers import MdoHelper
from apps.vartype.models import VarTypeOutputUnit
from iotile_cloud.utils.gid import IOTileStreamSlug, IOTileVariableSlug

from ..base import ReportGenerator


class ReportColumn(object):
    msgs = []
    name = None
    type = None
    output_units = None
    aggregate = None
    lids = []
    stream_slugs = []

    def __init__(self, obj):
        assert 'name' in obj
        assert 'type' in obj
        assert 'units' in obj
        assert 'aggregate' in obj
        assert 'vars' in obj and len(obj['vars'])
        self.msgs = []
        self.stream_slugs = []
        self.lids = []

        self.name = obj['name']
        self.type = obj['type']
        self.aggregate = obj['aggregate']

        try:
            self.output_units = VarTypeOutputUnit.objects.get(slug=obj['units'])
        except VarTypeOutputUnit.DoesNotExist:
            self.output_units = None


        for v in obj['vars']:
            if self._check_variable_item_ok(v):
                self.lids.append(v['lid'])

    def __str__(self):
        return self.name

    def _check_variable_item_ok(self, item):
        if isinstance(item, dict):
            if 'lid' in item and 'name' in item:
                id = item['lid']
                if isinstance(id, str) and len(id) == 4:
                    try:
                        int(id, 16)
                        return True
                    except ValueError:
                        pass
                self.msgs.append('Ignoring variable {}'.format(item['name']))
        else:
            self.msgs.append('Ignoring incorrectly formatted variable')
        return False

    def add_stream(self, stream, lid):
        if lid in self.lids:
            self.stream_slugs.append(stream.slug)
            return True
        return False


class ReportRows(object):
    msgs = []
    stream_slugs = []
    projects = {}

    def __init__(self):
        self.msgs = []
        self.stream_slugs = []
        self.projects= {}

    def add_stream(self, stream, lid):
        if stream.slug not in self.stream_slugs:
            self.stream_slugs.append(stream.slug)
            if stream.project.slug not in self.projects:
                self.projects[stream.project.slug] = {
                    'project': stream.project,
                    'devices': {
                        stream.device.slug: {
                            'device': stream.device,
                            'streams': [stream]
                        }
                    }
                }
            else:
                if stream.device.slug not in self.projects[stream.project.slug]['devices']:
                    self.projects[stream.project.slug]['devices'][stream.device.slug] = {
                        'device': stream.device,
                        'streams': [stream]
                    }
                else:
                    self.projects[stream.project.slug]['devices'][stream.device.slug]['streams'].append(stream)


class DefaultReportGenerator(ReportGenerator):
    _cols = {}
    _rows = None

    def __init__(self, msgs, rpt, start, end, sources=None):
        super(DefaultReportGenerator, self).__init__(msgs, rpt, start, end, sources)
        self._cols = []
        self._rows = ReportRows()

    def _email_template(self):
        return 'report/default'

    def _initial_value(self, aggregation_type):
        factory = {
            'sum': 0,
            'max': float('-inf'),
            'min': float('inf'),
        }
        return factory[aggregation_type]

    def _aggregate(self, val1, val2, aggregation_type):
        factory = {
            'sum': lambda val1, val2: val1 + val2,
            'max': lambda val1, val2: val1 if val1 >= val2 else val2,
            'min': lambda val1, val2: val1 if val1 <= val2 else val2,
        }
        return factory[aggregation_type](val1, val2)

    def _collect_stream_data_stats(self, stream, units, aggregate_type):
        qs = self._get_stream_data_qs(stream.slug)

        stats = qs.aggregate(
            sum=Sum('value'),
            max=Max('value'),
            min=Min('value'),
        )
        if aggregate_type in stats and stats[aggregate_type] != None:
            # Convert value to required report units
            if units:
                output_mdo = MdoHelper(units.m, units.d, units.o)
                return output_mdo.compute(stats[aggregate_type])
            return stats[aggregate_type]

        return 0

    def _compute_report_context(self):
        total = [{ 'value': self._initial_value(col.aggregate), 'units': ''} for col in self._cols]
        project_list = []
        projects = self._rows.projects
        for p_key in projects.keys():
            project = projects[p_key]['project']
            project_obj = {
                'name': project.name,
                'streams': [],
                'total': [{ 'value': self._initial_value(col.aggregate), 'units': ''} for col in self._cols]
            }
            for d_key in projects[p_key]['devices'].keys():
                # device = projects[p_key]['devices'][d_key]['device']
                for stream in projects[p_key]['devices'][d_key]['streams']:
                    row = {
                        'label': stream.project_ui_label
                    }
                    row['cols'] = []
                    col_index = 0
                    for col in self._cols:
                        if stream.slug in col.stream_slugs:
                            stream_value = self._collect_stream_data_stats(stream, col.output_units, col.aggregate)
                            stream_units = col.output_units.unit_short
                            item = {
                                'value': stream_value,
                                'units': stream_units
                            }
                            row['cols'].append(item)
                            project_obj['total'][col_index]['value'] = self._aggregate(
                                project_obj['total'][col_index]['value'], stream_value, col.aggregate
                            )
                            project_obj['total'][col_index]['units'] = stream_units
                            total[col_index]['value'] = self._aggregate(
                                total[col_index]['value'], stream_value, col.aggregate
                            )
                            total[col_index]['units'] = stream_units
                        col_index += 1
                    project_obj['streams'].append(row)
            project_list.append(project_obj)

        ctx = {
            'label': self._rpt.label,
            'start': self._start,
            'end': self._end,
            'headers': [col.name for col in self._cols],
            'project_list': project_list,
            'total': total
            }
        return ctx

    def add_streams_for_qs(self, qs):
        for stream in qs:
            stream_slug = IOTileStreamSlug(stream.slug)
            parts = stream_slug.get_parts()
            assert 'variable' in parts
            variable = IOTileVariableSlug(parts['variable'])
            lid = variable.formatted_local_id()
            for col in self._cols:
                if col.add_stream(stream, lid):
                    self._rows.add_stream(stream, lid)

    def process_config(self):

        for col_data in self._rpt.config['cols']:
            col = ReportColumn(col_data)
            self._msgs += col.msgs
            self._cols.append(col)


