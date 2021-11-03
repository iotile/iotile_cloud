import logging
from collections import OrderedDict

from django.core.cache import cache

from rest_framework import serializers

from .models import VarType, VarTypeInputUnit, VarTypeOutputUnit, VarTypeDecoder, VarTypeSchema

# Get an instance of a logger
logger = logging.getLogger(__name__)


class VarTypeField(serializers.PrimaryKeyRelatedField):

    def to_representation(self, value):
        serializer = VarTypeReadOnlySerializer(value)
        return serializer.data


class VarTypeUnitField(serializers.SlugRelatedField):

    def get_choices(self, cutoff=None):
        queryset = self.get_queryset()
        if queryset is None:
            return {}

        return OrderedDict([(item.id, self.display_value(item)) for item in queryset])


class VarTypeInputUnitField(VarTypeUnitField):
    queryset = VarTypeInputUnit.objects.all()

    def to_representation(self, value):
        slug = str(value.slug)
        try:
            if cache:
                result = cache.get(slug)
                if result:
                    # logger.debug('VarTypeUnit: cache(HIT)={0}'.format(slug))
                    return result
            serializer = VarTypeInputUnitSerializer(value)
            if cache:
                # logger.debug('VarTypeUnit: cache(SET)={0}'.format(slug))
                cache.set(slug, serializer.data)
            return serializer.data
        except VarTypeInputUnit.DoesNotExist:
            return None


class VarTypeOutputUnitField(VarTypeUnitField):
    queryset = VarTypeOutputUnit.objects.all()

    def to_representation(self, value):
        slug = str(value.slug)
        try:
            if cache:
                result = cache.get(slug)
                if result:
                    # logger.debug('VarTypeUnit: cache(HIT)={0}'.format(slug))
                    return result
            serializer = VarTypeOutputUnitSerializer(value)
            if cache:
                # logger.debug('VarTypeUnit: cache(SET)={0}'.format(slug))
                cache.set(slug, serializer.data)
            return serializer.data
        except VarTypeOutputUnit.DoesNotExist:
            return None


class VarTypeInputUnitSerializer(serializers.ModelSerializer):

    class Meta:
        model = VarTypeInputUnit
        fields = ('slug', 'unit_full', 'unit_short', 'm', 'd', 'o')
        read_only_fields = ('slug', )


class VarTypeOutputUnitSerializer(serializers.ModelSerializer):

    class Meta:
        model = VarTypeOutputUnit
        fields = ('slug', 'unit_full', 'unit_short', 'm', 'd', 'o', 'decimal_places', 'derived_units')
        read_only_fields = ('slug', )


class VarTypeDecoderSerializer(serializers.ModelSerializer):

    class Meta:
        model = VarTypeDecoder
        fields = ('id', 'raw_packet_format', 'packet_info')


class VarTypeSchemaSerializer(serializers.ModelSerializer):

    class Meta:
        model = VarTypeSchema
        fields = ('id', 'keys', 'display_order')


class VarTypeReadOnlySerializer(serializers.ModelSerializer):
    available_input_units = serializers.SerializerMethodField()
    available_output_units = serializers.SerializerMethodField()
    decoder = VarTypeDecoderSerializer(read_only=True)
    schema = VarTypeSchemaSerializer(read_only=True)
    storage_units_short = serializers.SerializerMethodField()

    class Meta:
        model = VarType
        fields = ('name', 'slug', 'available_input_units', 'available_output_units',
                  'stream_data_type', 'decoder', 'schema',
                  'storage_units_full', 'storage_units_short')
        read_only_fields = ('slug', )

    def get_available_input_units(self, obj):
        # return [u.unit_full for u in obj.input_units.all()]
        serializer = VarTypeInputUnitSerializer(obj.input_units.all(), many=True)
        return serializer.data

    def get_available_output_units(self, obj):
        # return [u.unit_full for u in obj.input_units.all()]
        serializer = VarTypeOutputUnitSerializer(obj.output_units.all(), many=True)
        return serializer.data

    def get_storage_units_short(self, obj):
        return ''
