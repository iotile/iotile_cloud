import logging

from rest_framework import serializers

from apps.org.models import Org
from apps.project.models import Project
from apps.stream.models import StreamId

from .models import *

# Get an instance of a logger
logger = logging.getLogger(__name__)


class StreamAliasSerializer(serializers.ModelSerializer):
    org = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Org.objects.all(),
    )
    created_by = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True,
    )
    gid = serializers.SerializerMethodField()

    class Meta:
        model = StreamAlias
        fields = (
            'id',
            'slug',
            'gid',
            'name',
            'org',
            'created_on',
            'created_by',
        )
        read_only_fields = (
            'slug',
            'created_on',
        )

    def get_gid(self, obj):
        return obj.formatted_gid


class StreamAliasTapSerializer(serializers.ModelSerializer):
    alias = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=StreamAlias.objects.all(),
    )
    stream = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=StreamId.objects.all(),
    )
    created_by = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True,
    )

    class Meta:
        model = StreamAliasTap
        fields = (
            'id',
            'alias',
            'timestamp',
            'stream',
            'created_on',
            'created_by',
        )
        read_only_fields = (
            'created_on',
        )

    def is_valid(self, *args, **kwargs):
        """
        Check that the stream belongs to the organization (and project)
        """
        if super(StreamAliasTapSerializer, self).is_valid(*args, **kwargs):
            # partial update (get existing alias or stream if none is given)
            if self.partial:
                alias = self.validated_data.get('alias', self.instance.alias)
                stream = self.validated_data.get('stream', self.instance.stream)
            # full update (get alias and stream from data)
            else:
                alias = self.validated_data['alias']
                stream = self.validated_data['stream']
            # check alias and stream are consistent for org
            if stream.org:
                if stream.org != alias.org:
                    raise serializers.ValidationError('Stream is not in the Org of Alias')
            return True
        return False
