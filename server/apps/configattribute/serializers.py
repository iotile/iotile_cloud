from rest_framework import serializers
from rest_framework import exceptions as drf_exceptions

from .models import *


class ConfigAttributeNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigAttributeName
        fields = ('id', 'name', 'description', 'tags', )


class ConfigAttributeSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=64)
    log_as_note = serializers.BooleanField(required=False, help_text='If true, log change as a System Note')
    class Meta:
        model = ConfigAttribute
        fields = ('id', 'target', 'name', 'data', 'updated_on', 'log_as_note')
        read_only_fields = ('updated_on', 'updated_by')
        extra_kwargs = {
            'log_as_note': {'write_only': True},
        }

    def create(self, validated_data):
        if 'data' in validated_data and 'target' in validated_data and 'name' in validated_data:
            name_str = validated_data.pop('name')
            try:
                name = ConfigAttributeName.objects.get(name=name_str)
            except ConfigAttributeName.DoesNotExist:
                raise drf_exceptions.ValidationError('Most use a valid Configuration Attribute Name')

            target = validated_data['target']
            obj = ConfigAttribute.objects.get_or_create_attribute(
                target=target,
                data=validated_data['data'],
                name=name,
                updated_by=validated_data['updated_by']
            )

            return obj
        raise drf_exceptions.ValidationError('Required fields: data, target, name')

    def update(self, instance, validated_data):
        """
        Only update data field
        """
        if 'data' not in validated_data:
            raise drf_exceptions.ValidationError('Required field: data')
        instance.data = validated_data.get('data')
        instance.updated_by = validated_data.get('updated_by')
        instance.save()
        return instance
