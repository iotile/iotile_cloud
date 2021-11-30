import json

from django.shortcuts import get_object_or_404
from django.template.defaultfilters import slugify

from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.utils import get_stream_output_mdo, get_stream_output_unit
from apps.utils.gid.convert import formatted_gfid
from apps.utils.mdo.helpers import MdoHelper

from .models import *


class StreamFilterActionSerializer(serializers.ModelSerializer):

    class Meta:
        model = StreamFilterAction
        fields = ('id', 'type', 'on', 'extra_payload', 'state')


class StreamFilterTriggerSerializer(serializers.ModelSerializer):

    class Meta:
        model = StreamFilterTrigger
        fields = ('id', 'operator', 'get_operator_display', 'threshold', 'user_threshold', 'user_output_unit', 'user_unit_full', 'transition')
        read_only_fields = ('id', 'get_operator_display', 'threshold', 'user_output_unit', 'user_unit_full')
        extra_kwargs = {'transition': {'write_only': True, 'required': False}}

    def validate(self, data):
        if 'filter' in self.context and 'transition' in data and self.context['filter'] != data['transition'].filter:
            raise serializers.ValidationError("Invalid transition")
        return data

    def create(self, validated_data):
        if 'filter' in self.context:
            f = self.context['filter']
        elif 'transition' in validated_data:
            f = validated_data['transition'].filter
        else:
            raise serializers.ValidationError('Filter or transition not provided')
        if f and f.input_stream:
            output_unit = get_stream_output_unit(f.input_stream)
            output_mdo = get_stream_output_mdo(f.input_stream)
        else:
            output_unit = f.variable.output_unit
            var = f.variable
            output_mdo = MdoHelper(var.multiplication_factor, var.division_factor, var.offset)
        if validated_data['user_threshold'] is not None and output_mdo:
            threshold_internal_value = output_mdo.compute_reverse(validated_data['user_threshold'])
        else:
            threshold_internal_value = None
        obj = StreamFilterTrigger.objects.create(filter=f, user_output_unit=output_unit, threshold=threshold_internal_value, **validated_data)
        return obj


class StateReadOnlySerializer(serializers.ModelSerializer):
    actions = StreamFilterActionSerializer(read_only=True, many=True)

    class Meta:
        model = State
        fields = ('id', 'label', 'slug', 'actions')


class StateTransitionReadOnlySerializer(serializers.ModelSerializer):
    triggers = StreamFilterTriggerSerializer(read_only=True, many=True)
    # src = StateReadOnlySerializer(read_only=True)
    # dst = StateReadOnlySerializer(read_only=True)

    class Meta:
        model = StateTransition
        fields = ('id', 'src', 'dst', 'triggers')


class StreamFilterSerializer(serializers.ModelSerializer):
    input_stream = serializers.SlugRelatedField(
        read_only=True,
        slug_field='slug',
        required=False
    )
    project = serializers.SlugRelatedField(
        queryset=Project.objects.all(),
        slug_field='slug',
        required=True
    )
    device = serializers.SlugRelatedField(
        queryset=Device.objects.all(),
        slug_field='slug',
        required=False
    )
    variable = serializers.SlugRelatedField(
        queryset=StreamVariable.objects.all(),
        slug_field='slug',
        required=True
    )

    transitions = StateTransitionReadOnlySerializer(read_only=True, many=True)
    states = StateReadOnlySerializer(read_only=True, many=True)

    class Meta:
        model = StreamFilter
        fields = ('id', 'slug', 'name', 'input_stream', 'project', 'variable', 'device', 'active', 'states',
                  'transitions', 'created_on', 'created_by')
        read_only_fields = ('created_on', 'created_by', 'slug', 'active', 'transitions')

    def validate(self, data):
        device = data['device'] if 'device' in data else None
        variable = data['variable']
        project = data['project']
        if device:
            streams = StreamId.objects.filter(device=device, variable=variable,
                                              project=project, block__isnull=True)
            if streams:
                stream = streams[0]
                elements = stream.slug.split('--')
                filter_stream_key = '--'.join(['f', ] + elements[1:])
                if StreamFilter.objects.filter(slug=filter_stream_key).count() > 0:
                    raise serializers.ValidationError("Filter for this stream already exists")
                data['input_stream'] = stream
            else:
                raise serializers.ValidationError("Stream corresponding to this device and variable does not exist")
        else:
            filter_stream_key = formatted_gfid(pid=project.formatted_gid,
                                               did=None,
                                               vid=variable.formatted_lid)
            if StreamFilter.objects.filter(slug=filter_stream_key).count() > 0:
                raise serializers.ValidationError("Filter already exists")
        return data


class StateTransitionSerializer(serializers.ModelSerializer):
    triggers = StreamFilterTriggerSerializer(required=False, many=True)

    class Meta:
        model = StateTransition
        fields = ('src', 'dst', 'triggers')

    def validate(self, data):
        if 'filter' in self.context:
            if not (data['src'].filter == self.context['filter'] and data['dst'].filter == self.context['filter']):
                raise serializers.ValidationError("Src and dst must be states of the filter in serializer context")
            f = self.context['filter']
        else:
            if data['src'] and (data['src'].filter != data['dst'].filter):
                raise serializers.ValidationError("Src and dst must be states of a same filter ")
            f = data['src'].filter
        if StateTransition.objects.filter(src=data['src'], dst=data['dst'], filter=f).count() > 0 and 'request' in self.context and self.context['request'].method == 'POST':
            raise serializers.ValidationError("Transition already exists")
        return data

    def create(self, validated_data):
        trigger_data = None
        if 'triggers' in validated_data:
            trigger_data = validated_data.pop('triggers')
        transition = StateTransition.objects.create(**validated_data)
        if trigger_data:
            for item in trigger_data:
                item['transition'] = str(transition.id)
            trigger_serializer = StreamFilterTriggerSerializer(data=trigger_data, many=True)
            if trigger_serializer.is_valid() and 'request' in self.context:
                trigger_serializer.save(created_by=self.context['request'].user)
        return transition

    def update(self, instance, validated_data):
        if 'triggers' in validated_data:
            for t in instance.triggers.all():
                t.delete()
            trigger_data = validated_data['triggers']
            for item in trigger_data:
                item['transition'] = str(instance.id)
            trigger_serializer = StreamFilterTriggerSerializer(data=trigger_data, many=True)
            if trigger_serializer.is_valid() and 'request' in self.context:
                trigger_serializer.save(created_by=self.context['request'].user)
        return instance


class StateSerializer(serializers.ModelSerializer):
    actions = StreamFilterActionSerializer(read_only=True, many=True)

    class Meta:
        model = State
        fields = ('id', 'label', 'actions')

    def validate(self, data):
        if 'filter' in self.context and 'request' in self.context and self.context['request'].method == 'POST' and State.objects.filter(slug=slugify(data['label']), filter=self.context['filter']).count() > 0:
            raise serializers.ValidationError("State already exists")
        return data
