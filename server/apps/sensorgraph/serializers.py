from rest_framework import serializers

from .models import *


class VariableTemplateSerializer(serializers.ModelSerializer):
    var_type = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=VarType.objects.all()
    )
    default_input_unit = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=VarTypeInputUnit.objects.all(),
        allow_null=True
    )
    default_output_unit = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=VarTypeOutputUnit.objects.all(),
        allow_null=True
    )
    sg = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=SensorGraph.objects.all()
    )

    class Meta:
        model = VariableTemplate
        fields = ('id', 'label', 'sg', 'lid_hex', 'derived_lid_hex', 'var_type', 'default_input_unit', 'default_output_unit',
                  'ctype', 'm', 'd', 'o', 'app_only', 'web_only')



class VariableTemplateReadOnlySerializer(serializers.ModelSerializer):
    var_type = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True,
        style={'base_template': 'input.html'}
    )
    default_input_unit = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True,
        style={'base_template': 'input.html'}
    )
    default_output_unit = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True,
        style={'base_template': 'input.html'}
    )

    class Meta:
        model = VariableTemplate
        fields = ('id', 'label', 'lid_hex', 'derived_lid_hex', 'var_type', 'default_input_unit', 'default_output_unit',
                  'ctype', 'm', 'd', 'o', 'app_only', 'web_only')


class DisplayWidgetTemplateSerializer(serializers.ModelSerializer):
    var_type = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=VarType.objects.all(),
        required=False,
        allow_null=True
    )
    sg = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=SensorGraph.objects.all()
    )

    class Meta:
        model = DisplayWidgetTemplate
        fields = ('id', 'label', 'sg', 'lid_hex', 'type', 'args',
                  'var_type', 'derived_unit_type', 'show_in_app', 'show_in_web')


class DisplayWidgetTemplateReadOnlySerializer(serializers.ModelSerializer):
    var_type = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True,
        style={'base_template': 'input.html'}
    )

    class Meta:
        model = DisplayWidgetTemplate
        fields = ('id', 'label', 'lid_hex', 'type', 'args',
                  'var_type', 'derived_unit_type', 'show_in_app', 'show_in_web')


class SensorGraphSerializer(serializers.ModelSerializer):
    org = serializers.SlugRelatedField(
        queryset=Org.objects.filter(is_vendor=True),
        slug_field='slug',
        style={'base_template': 'input.html'}
    )
    project_template = serializers.SlugRelatedField(
        queryset=ProjectTemplate.objects.filter(active=True),
        slug_field='slug',
        required=False,
        style={'base_template': 'input.html'}
    )
    variable_templates = VariableTemplateReadOnlySerializer(many=True, read_only=True)
    display_widget_templates = DisplayWidgetTemplateReadOnlySerializer(many=True, read_only=True)
    class Meta:
        model = SensorGraph
        fields = ('id', 'name', 'slug', 'org',
                  'project_template', 'variable_templates', 'display_widget_templates',
                  'ui_extra', 'report_processing_engine_ver',
                  'major_version', 'minor_version', 'patch_version', 'version',
                  'app_tag', 'app_major_version', 'app_minor_version', 'app_version',
                  'created_on', )
        read_only_fields = ('created_on', 'slug', 'version')
        extra_kwargs = {
            """ TODO: Enable once we fix SDKs
            'major_version': {'write_only': True},
            'minor_version': {'write_only': True},
            'patch_version': {'write_only': True},
            """
            'app_major_version': {'write_only': True},
            'app_minor_version': {'write_only': True},
        }

class SensorGraphAddOrgTemplateSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=True)
