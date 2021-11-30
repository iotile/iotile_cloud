import json
import logging
import os

from django.core.management.base import BaseCommand

from apps.authentication.models import Account
from apps.vartype.models import VarType, VarTypeDecoder, VarTypeInputUnit, VarTypeOutputUnit, VarTypeSchema
from apps.vartype.types import STREAM_DATA_TYPE_CHOICES

logger = logging.getLogger(__name__)


class Command(BaseCommand):

    def _get_data_file_path(self, filename):
        path = os.path.join(os.path.dirname(__file__), 'var-type-data', filename)
        return path

    def parse_var_type(self, user):
        count =0
        path = os.path.join(os.path.dirname(__file__), 'var-type-data')
        for filename in os.listdir(path):
            with open(self._get_data_file_path(filename)) as infile:
                data = json.load(infile)
            if data:
                count +=1
                if 'name' in data:
                    try:
                        vt = VarType.objects.get(name=data['name'])
                    except VarType.DoesNotExist:
                        # create a new var type if not exist.
                        vt = VarType.objects.create(
                            name=data['name'],
                            storage_units_full=data['storage_units_full'],
                            created_by=user
                        )
                if 'available_input_units' in data and data['available_input_units']:
                    self.create_update_input_units(data, vt, user)
                if 'available_output_units' in data and data['available_output_units']:
                    self.create_update_output_units(data, vt, user)
                if 'data_type' in data:
                    assert data['data_type'] in [t[0] for t in STREAM_DATA_TYPE_CHOICES]
                    vt.stream_data_type = data['data_type']
                if 'decoder' in data and data['decoder']:
                    self.create_decoder(data, vt, user)
                if 'schema' in data and data['schema']:
                    self.create_schema(data, vt, user)
                vt.save()
                logger.info('Finish create or update var type ' + vt.slug)
            else:
                logger.error('Data non valid.')
        return count

    def create_decoder(self, data, vt, user):
        try:
            decoder = vt.decoder
            decoder.raw_packet_format=data['decoder']['raw_packet_format']
            decoder.packet_info=data['decoder']['packet_info']
            decoder.save()
        except Exception as e:
            logger.info(e)
            VarTypeDecoder.objects.create(
                var_type=vt, created_by=user,
                raw_packet_format=data['decoder']['raw_packet_format'],
                packet_info=data['decoder']['packet_info']
            )

    def create_schema(self, data, vt, user):
        if 'display_order' not in data['schema']:
            data['schema']['display_order'] = []
        try:
            schema = vt.schema
            schema.keys = data['schema']['keys']
            schema.display_order = data['schema']['display_order']
            schema.save()
        except Exception as e:
            logger.info(e)
            VarTypeSchema.objects.create(
                var_type=vt, created_by=user,
                keys=data['schema']['keys'],
                display_order=data['schema']['display_order']
            )

    def create_update_input_units(self, data, vt, user):
        input_json_list = []
        for i in data['available_input_units']:
            offset = 0.0
            if 'unit_full' in i:
                input_json_list += [i['unit_full']]
                if 'o' in i:
                    offset = i['o']
                try:
                    VarTypeInputUnit.objects.get(unit_full=i['unit_full'],
                                                 var_type=vt)
                    # update if Variable template exists
                    VarTypeInputUnit.objects.filter(unit_full=i['unit_full'],
                                                    var_type=vt).update(unit_short=i['unit_short'],
                                                                        var_type=vt,
                                                                        m=i['m'],
                                                                        d=i['d'],
                                                                        o=offset)
                except VarTypeInputUnit.DoesNotExist:
                    VarTypeInputUnit.objects.create(
                        unit_full=i['unit_full'],
                        unit_short=i['unit_short'],
                        var_type=vt,
                        m=i['m'],
                        d=i['d'],
                        o=offset,
                        created_by=user
                    )

        # Give warning if database has additional data
        input_database_list = VarTypeInputUnit.objects.filter(var_type=vt)
        if not len(input_database_list) == len(input_json_list):
            for i in input_database_list:
                if i.unit_full not in input_json_list:
                    logger.warning('Found record not in json file: VarTypeInput - {}'.format(i.unit_full))
                    # VarTypeInputUnit.objects.filter(unit_full=i['unit_full'], var_type=vt).delete()

    def create_update_output_units(self, data, vt, user):
        output_json_list = []
        for o in data['available_output_units']:
            offset = 0.0
            if 'unit_full' in o:
                if 'o' in o:
                    offset = o['o']
                output_json_list += [o['unit_full']]
                try:
                    VarTypeOutputUnit.objects.get(unit_full=o['unit_full'],
                                                  var_type=vt)
                    # update if Variable template exists
                    VarTypeOutputUnit.objects.filter(unit_full=o['unit_full'],
                                                     var_type=vt).update(unit_short=o['unit_short'],
                                                                         var_type=vt,
                                                                         m=o['m'],
                                                                         d=o['d'],
                                                                         o=offset,
                                                                         decimal_places=o['decimal_places'],
                                                                         derived_units=o['derived_units'])
                except VarTypeOutputUnit.DoesNotExist:
                    VarTypeOutputUnit.objects.create(
                        unit_full=o['unit_full'],
                        unit_short=o['unit_short'],
                        var_type=vt,
                        m=o['m'],
                        d=o['d'],
                        o=offset,
                        decimal_places=o['decimal_places'],
                        derived_units=o['derived_units'],
                        created_by=user
                    )
        # make sure that the var type in database doesn't have more variables than in the json file
        output_database_list = VarTypeOutputUnit.objects.filter(var_type=vt)
        if not len(output_database_list) == len(output_json_list):
            for o in output_database_list:
                if o.unit_full not in output_json_list:
                    logger.warning('Found record not in json file: VarTypeOutput - {}'.format(o.unit_full))
                    # VarTypeOutputUnit.objects.filter(unit_full=o['unit_full'], var_type=vt).delete()

    def handle(self, *args, **options):
        admin = Account.objects.get_admin()
        total = self.parse_var_type(admin)
        if not total == VarType.objects.all().count():
            logger.warning("The number of var types in database and in json files don't match ! "
                           "Found {0} in json file. Found {1} in database".format(total,
                                                                                  VarType.objects.all().count()))
        logger.info('Complete updating var type')
