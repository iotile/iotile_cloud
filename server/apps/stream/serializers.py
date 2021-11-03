import logging

from rest_framework import serializers

from apps.vartype.serializers import VarTypeInputUnitField, VarTypeOutputUnitField
from apps.vartype.models import VarType
from apps.physicaldevice.models import Device
from apps.utils.gid.convert import gid_split, gid_join

from .models import StreamId, StreamVariable

# Get an instance of a logger
logger = logging.getLogger(__name__)


class StringListField(serializers.ListField):
    child = serializers.CharField(max_length=64)


class StreamVariableSerializer(serializers.ModelSerializer):
    org = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug'
    )
    var_type = serializers.SlugRelatedField(
        queryset=VarType.objects.all(),
        slug_field='slug',
        required=False
    )
    derived_variable = serializers.SlugRelatedField(
        queryset=StreamVariable.objects.all(),
        slug_field='slug',
        required=False
    )
    lid = serializers.IntegerField(help_text='Variable ID configured on the Device Sensor Graph')
    input_unit = VarTypeInputUnitField(required=False, slug_field = 'slug')
    output_unit = VarTypeOutputUnitField(required=False, slug_field = 'slug')

    class Meta:
        model = StreamVariable
        fields = ('id', 'name', 'lid', 'var_type', 'input_unit', 'output_unit',
                  'derived_variable', 'project', 'org', 'about', 'created_on', 'raw_value_format',
                  'units', 'multiplication_factor', 'division_factor', 'offset', 'decimal_places',
                  'mdo_label', 'web_only', 'app_only', 'slug',)
        read_only_fields = ('created_on', 'org', 'slug', )


class StreamIdSerializer(serializers.ModelSerializer):
    org = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug'
    )
    project = serializers.SerializerMethodField(read_only=True)
    device = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug'
    )
    block = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug'
    )
    variable = serializers.SerializerMethodField(read_only=True)
    var_type = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug'
    )
    derived_stream = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug'
    )
    input_unit = VarTypeInputUnitField(required=False, slug_field = 'slug')
    output_unit = VarTypeOutputUnitField(required=False, slug_field = 'slug')
    class Meta:
        model = StreamId
        fields = ('id', 'project_id', 'project', 'device', 'block', 'data_label',
                  'variable', 'var_type', 'data_type', 'var_name', 'var_lid',
                  'input_unit', 'output_unit',
                  'data_label', 'derived_stream', 'raw_value_format',
                  'mdo_type', 'mdo_label', 'multiplication_factor', 'division_factor', 'offset',
                  'org', 'created_on', 'slug', 'data_label', 'enabled')
        read_only_fields = ('created_on', 'org', 'slug', 'project_id')

    def get_variable(self, obj):
        parts = gid_split(obj.slug)
        return gid_join(['v', parts[1], parts[3]])

    def get_project(self, obj):
        parts = gid_split(obj.slug)
        return gid_join(['p', parts[1]])


class StreamIdCreateSerializer(serializers.ModelSerializer):
    org = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug'
    )
    device = serializers.SlugRelatedField(
        queryset=Device.objects.filter(active=True),
        slug_field='slug',
        required=False
    )
    variable = serializers.SlugRelatedField(
        queryset=StreamVariable.objects.all(),
        slug_field='slug',
        required=True
    )
    project = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug'
    )
    var_type = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug'
    )
    class Meta:
        model = StreamId
        fields = ('id', 'project', 'device', 'data_label',
                  'variable', 'var_type', 'data_type',
                  'multiplication_factor', 'division_factor', 'offset',
                  'org', 'created_on', 'slug', 'created_by')
        read_only_fields = ('created_on', 'org', 'slug', 'project', 'created_by',
                            'multiplication_factor', 'division_factor', 'offset')
