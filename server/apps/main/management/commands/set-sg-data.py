from django.core.management.base import BaseCommand
import os
import sys
import json
import logging
from django.template.defaultfilters import slugify
from apps.sensorgraph.models import DisplayWidgetTemplate, SensorGraph, VariableTemplate
from apps.org.models import Org
from apps.authentication.models import Account
from apps.projecttemplate.models import ProjectTemplate
from apps.vartype.models import VarType, VarTypeInputUnit, VarTypeOutputUnit

logger = logging.getLogger(__name__)


class Command(BaseCommand):

    def _get_data_file_path(self, filename):
        path = os.path.join(os.path.dirname(__file__), 'sg-data', filename)
        return path

    def parse_sg(self, user):
        count = 0
        path = os.path.join(os.path.dirname(__file__), 'sg-data')
        for filename in os.listdir(path):
            with open(self._get_data_file_path(filename)) as infile:
                data = json.load(infile)
            if data:
                sg = None
                count += 1
                if 'name' in data and 'minor_version' in data and 'major_version' in data and 'patch_version' in data:
                    expected_slug = slugify('{0}--v{1}-{2}-{3}'.format(data['name'],
                                                                       data['major_version'],
                                                                       data['minor_version'],
                                                                       data['patch_version']))
                    if 'report_processing_engine_ver' not in data:
                        data['report_processing_engine_ver'] = 0

                    try:
                        sg = SensorGraph.objects.get(slug=expected_slug)
                    except SensorGraph.DoesNotExist:
                        # create a new sensor gragh if not exist.
                        sg = SensorGraph.objects.create_graph(
                            org=None,
                            created_by=user,
                            name=data['name'],
                            project_template=None,
                            report_processing_engine_ver=data['report_processing_engine_ver'],
                            minor_version=data['minor_version'],
                            major_version=data['major_version'],
                            patch_version=data['patch_version']
                        )
                if not sg:
                    logger.error('Error parsing SG')
                    sys.exit(1)
                logger.info('Processing sensor graph ' + sg.slug)
                # update
                if 'org' in data:
                    try:
                        sg.org = Org.objects.get(slug=data['org'])
                    except Org.DoesNotExist:
                        logger.error('Organization slug ' + data['org'] + ' does not exist!')
                        sg.delete()
                        sys.exit(1)
                if 'project_template' in data:
                    try:
                        sg.project_template = ProjectTemplate.objects.get(slug=data['project_template'])
                    except ProjectTemplate.DoesNotExist:
                        sg.delete()
                        logger.error('Project template slug' + data['project_template'] + 'does not exist!')
                        sys.exit(1)
                if 'ui_extra' in data:
                    sg.ui_extra = data['ui_extra']
                if 'description' in data:
                    sg.description = data['description']
                if 'report_processing_engine_ver' in data:
                    sg.report_processing_engine_ver = data['report_processing_engine_ver']
                if 'app_tag' in data:
                    sg.app_tag = data['app_tag']
                if 'app_version' in data:
                    app_ver = data['app_version'].split('.')
                    if len(app_ver) > 0:
                        sg.app_major_version = int(app_ver[0])
                    if len(app_ver) > 1:
                        sg.app_minor_version = int(app_ver[1])

                # Generate all associated templates: Variables and Widgets
                self._create_update_variable_template(data, sg, user)
                self._create_update_display_widget(data, sg, user)

                sg.save()
                logger.info('-> Finish create or update sensor graph ' + sg.slug)
            else:
                logger.error('Data non valid.')
                sys.exit(1)
        #  number of sensor graph json file (with data)
        return count

    def _create_update_variable_template(self, data, sg, user):
        var_json_list = []
        for vt in data['variable_templates']:
            input_unit = output_unit = None
            if 'lid_hex' in vt:
                var_json_list += [vt['lid_hex']]
                try:
                    var_type = VarType.objects.get(slug=vt['var_type'])
                except VarType.DoesNotExist:
                    logger.error('Invalid VarType: {}'.format(vt['var_type']))
                    sys.exit(1)
                if 'default_input_unit' in vt and vt['default_input_unit']:
                    try:
                        input_unit = VarTypeInputUnit.objects.get(slug=vt['default_input_unit'])
                    except VarTypeInputUnit.DoesNotExist:
                        logger.error('Invalid VarTypeInputUnit: {}'.format(vt['default_input_unit']))
                        sys.exit(1)
                if 'default_output_unit' in vt and vt['default_output_unit']:
                    try:
                        output_unit = VarTypeOutputUnit.objects.get(slug=vt['default_output_unit'])
                    except VarTypeOutputUnit.DoesNotExist:
                        logger.error('Invalid VarTypeOutputUnit: {}'.format(vt['default_output_unit']))
                        sys.exit(1)

                m = vt['m'] if 'm' in vt else 1
                d = vt['d'] if 'd' in vt else 1
                o = vt['o'] if '0' in vt else 0.0

                try:
                    # consider that lid_hex is unique within a sensor graph
                    v = sg.variable_templates.get(lid_hex=vt['lid_hex'])
                    # v = VariableTemplate.objects.get(lid_hex=var['lid_hex'], sg=sg)
                    v.label = vt['label']
                    if 'derived_lid_hex' in vt:
                        v.derived_lid_hex = vt['derived_lid_hex']
                    v.var_type = var_type
                    if 'ctype' in vt:
                        v.ctype=vt['ctype']
                    v.default_input_unit = input_unit
                    v.default_output_unit = output_unit
                    v.m = m
                    v.d = d
                    v.o = o
                    v.app_only = vt['app_only']
                    v.web_only = vt['web_only']
                    v.save()
                except VariableTemplate.DoesNotExist:
                    v = VariableTemplate.objects.create(
                        label=vt['label'],
                        sg=sg,
                        lid_hex=vt['lid_hex'],
                        var_type=var_type,
                        default_input_unit=input_unit,
                        default_output_unit=output_unit,
                        derived_lid_hex=vt['derived_lid_hex'] if 'derived_lid_hex' in vt else '',
                        ctype=vt['ctype'] if 'ctype' in vt else 'unsigned int',
                        m=m,
                        d=d,
                        o=o,
                        app_only=vt['app_only'],
                        web_only=vt['web_only'],
                        created_by=user
                    )
                    logger.info('-> New VariableTemplate: ID={0}, LID={1}'.format(v.id, v.lid_hex))
            else:
                logger.error('-> Illegal Variable Template: {}'.format(str(vt)))
                sys.exit(1)

        # make sure that the sensor graph in database doesn't have more variables than in the json file
        var_database_list = VariableTemplate.objects.filter(sg=sg)
        if not len(var_database_list) == len(var_json_list):
            for var in var_database_list:
                if var.lid_hex not in var_json_list:
                    logger.warning('Found record not in json file: VariableTemplate lid_hex - {}'.format(var.id))

    def _create_update_display_widget(self, data, sg, user):
        dw_json_list = []
        for dw in data['display_widget_templates']:
            if 'lid_hex' in dw and 'derived_unit_type' in dw:
                if 'type' not in dw:
                    # Set default type if no type
                    dw['type'] = 'val'
                try:
                    var_type = VarType.objects.get(slug=dw['var_type'])
                except VarType.DoesNotExist:
                    logger.error('Invalid VarType: {0} ({1})'.format(dw['var_type'], dw['lid_hex']))
                    sys.exit(1)
                try:
                    # consider that the combination lid_hex and derived_unit_type is unique within a sensor graph
                    d = DisplayWidgetTemplate.objects.get(lid_hex=dw['lid_hex'],
                                                          label=dw['label'],
                                                          derived_unit_type=dw['derived_unit_type'],
                                                          type=dw['type'],
                                                          sg=sg)
                    d.label=dw['label']
                    d.var_type = var_type
                    d.show_in_app = dw['show_in_app']
                    d.show_in_web = dw['show_in_web']
                    if 'args' in dw:
                        d.args = dw['args']
                    d.save()

                except DisplayWidgetTemplate.DoesNotExist:
                    d = DisplayWidgetTemplate(
                        label=dw['label'],
                        sg=sg,
                        type=dw['type'],
                        lid_hex=dw['lid_hex'],
                        var_type=var_type,
                        derived_unit_type=dw['derived_unit_type'],
                        show_in_app=dw['show_in_app'],
                        show_in_web=dw['show_in_web'],
                        created_by=user
                    )
                    if 'args' in dw:
                        d.args = dw['args']
                    d.save()
                    logger.info('-> New Display Widget: ID={0} Label={1}'.format(d.id, d.label))
                dw_json_list += [d.id]
            else:
                logger.error('-> Illegal DisplayWidget: {}'.format(str(dw)))
                sys.exit(1)

        # make sure that the sensor graph in database doesn't have more variables than in the json file
        dw_database_list = DisplayWidgetTemplate.objects.filter(sg=sg)
        if not len(dw_database_list) == len(dw_json_list):
            for dw in dw_database_list:
                if dw.id not in dw_json_list:
                    logger.warning('Found record not in json file: DisplayWidgetTemplate id - {}'.format(dw.id))

    def handle(self, *args, **options):
        admin = Account.objects.get_admin()
        total = self.parse_sg(admin)
        if not total == len(SensorGraph.objects.all()):
            logger.warning("The number of sensor graph in database and in json files don't match ! "
                           "Found {0} in json file. Found {1} in database".format(total,
                                                                                  len(SensorGraph.objects.all())))
        logger.info('Complete updating sensor graph')
