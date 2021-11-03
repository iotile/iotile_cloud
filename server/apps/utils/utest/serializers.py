
from rest_framework import serializers

from apps.vartype.models import *
from apps.vartype.serializers import (
    VarTypeInputUnitSerializer, VarTypeOutputUnitSerializer,
    VarTypeDecoderSerializer, VarTypeSchemaSerializer
)



class VarTypeSerializer(serializers.ModelSerializer):
    decoder = VarTypeDecoderSerializer(required=False)
    schema = VarTypeSchemaSerializer(required=False)
    available_input_units = VarTypeInputUnitSerializer(many=True)
    available_output_units = VarTypeOutputUnitSerializer(many=True)

    class Meta:
        model = VarType
        fields = ('name', 'slug', 'available_input_units', 'available_output_units', 'decoder', 'schema',
                  'storage_units_full', 'stream_data_type')
        read_only_fields = ('slug', )

    def create(self, validated_data):
        available_input_units = validated_data.pop('available_input_units')
        available_output_units = validated_data.pop('available_output_units')
        if 'decoder' in validated_data:
            decoder = validated_data.pop('decoder')
        else:
            decoder = None
        if 'schema' in validated_data:
            schema = validated_data.pop('schema')
        else:
            schema = None

        var_type = VarType.objects.create(**validated_data)

        for unit_data in available_input_units:
            VarTypeInputUnit.objects.create(var_type=var_type, created_by=var_type.created_by, **unit_data)

        for unit_data in available_output_units:
            VarTypeOutputUnit.objects.create(var_type=var_type, created_by=var_type.created_by, **unit_data)

        if decoder:
            VarTypeDecoder.objects.create(var_type=var_type, created_by=var_type.created_by, **decoder)
        if schema:
            VarTypeSchema.objects.create(var_type=var_type, created_by=var_type.created_by, **schema)

        return var_type

