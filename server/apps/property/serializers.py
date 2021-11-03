from django.conf import settings

from rest_framework import serializers

from .models import *


class TargetPropertyReadOnlySerializer(serializers.ModelSerializer):
    class Meta:
        model = GenericProperty
        fields = ('id', 'name', 'value', 'type', 'is_system')
        read_only_fields = ('value', 'type')


class PostPropertySerializer(serializers.Serializer):
    name = serializers.CharField(required=True)
    int_value = serializers.IntegerField(required=False, write_only=True)
    str_value = serializers.CharField(required=False, write_only=True, max_length=256, allow_blank=True)
    bool_value = serializers.BooleanField(required=False, write_only=True)
    is_system = serializers.BooleanField(required=False, default=False)

    class Meta:
        fields = ('name', 'int_value', 'str_value', 'bool_value', 'is_system')


class GenericPropertyReadOnlySerializer(serializers.ModelSerializer):
    class Meta:
        model = GenericProperty
        fields = ('id', 'name', 'value', 'type', 'is_system', 'target')
        read_only_fields = ('value', 'type', 'created_by', 'created_on')


class GenericPropertyWriteOnlySerializer(serializers.ModelSerializer):
    int_value = serializers.IntegerField(required=False, write_only=True)
    str_value = serializers.CharField(required=False, write_only=True, max_length=256, allow_blank=True)
    bool_value = serializers.BooleanField(required=False, write_only=True)
    is_system = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = GenericProperty
        fields = ('target', 'name', 'int_value', 'str_value', 'bool_value', 'is_system', 'value')
        read_only_fields = ('value', 'type', 'created_by', 'created_on')

    def validate(self, data):
        type_count = int('int_value' in data)
        type_count += int('str_value' in data)
        type_count += int('bool_value' in data)
        if type_count != 1:
            raise serializers.ValidationError('Only one of int_value, str_value, or bool_value can be used')

        return data

    def create(self, validated_data):
        prop = None
        target = validated_data['target']
        name = validated_data['name']
        is_system = validated_data['is_system']
        created_by = validated_data['created_by']
        if 'int_value' in validated_data:
            v = validated_data['int_value']
            prop = GenericProperty.objects.create_int_property(slug=target, name=name, value=v,
                                                               is_system=is_system, created_by=created_by)
        if 'str_value' in validated_data:
            v = validated_data['str_value']
            prop = GenericProperty.objects.create_str_property(slug=target, name=name, value=v,
                                                               is_system=is_system, created_by=created_by)
        if 'bool_value' in validated_data:
            v = validated_data['bool_value']
            prop = GenericProperty.objects.create_bool_property(slug=target, name=name, value=v,
                                                                is_system=is_system, created_by=created_by)

        return prop

    def update(self, instance, validated_data):
        if 'int_value' in validated_data:
            instance.set_int_value(validated_data['int_value'])
        if 'str_value' in validated_data:
            instance.set_str_value(validated_data['str_value'])
        if 'bool_value' in validated_data:
            instance.set_bool_value(validated_data['bool_value'])
        instance.save()
        return instance


class GenericPropertyOrgEnumSerializer(serializers.ModelSerializer):
    created_by = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True,
        style={'base_template': 'input.html'}
    )
    org = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True,
        style={'base_template': 'input.html'}
    )

    class Meta:
        model = GenericPropertyOrgEnum
        fields = ('id', 'org', 'value', 'template', 'created_by')
        read_only_fields = ('created_on', 'created_by', 'org', 'template')

    def create(self, validated_data):
        # Ensure that if value already exist, we don't create a new one
        enum, created = GenericPropertyOrgEnum.objects.get_or_create(
            value=validated_data['value'],
            template=validated_data['template'],
            defaults=validated_data
        )
        return enum


class GenericPropertyOrgTemplateSerializer(serializers.ModelSerializer):
    created_by = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True,
        style={'base_template': 'input.html'}
    )
    org = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Org.objects.all(),
        style={'base_template': 'input.html'}
    )
    enums = serializers.SerializerMethodField()

    class Meta:
        model = GenericPropertyOrgTemplate
        fields = ('id', 'org', 'type', 'name', 'default', 'enums', 'extra', 'created_by')
        read_only_fields = ('created_on', 'created_by',)

    def get_enums(self, obj):
        return [e.value for e in obj.enums.all()]
