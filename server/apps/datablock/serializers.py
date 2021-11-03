import logging
from django.contrib.auth import get_user_model
from django.utils.timezone import localtime
from django.db.models import Count

from rest_framework import serializers

from apps.physicaldevice.models import Device
from apps.org.models import Org
from apps.stream.models import StreamId
from apps.verticals.utils import get_data_block_vertical_helper
from apps.utils.data_helpers.manager import DataManager

from .tasks import schedule_archive
from .models import DataBlock, get_block_id

user_model = get_user_model()
logger = logging.getLogger(__name__)


class DataBlockSerializer(serializers.ModelSerializer):
    _pid = None
    created_by = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    device = serializers.SlugRelatedField(
        queryset=Device.objects.all(),
        slug_field='slug',
        write_only=True,
        required=True
    )
    sg = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    org = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    on_complete = serializers.JSONField(required=False)
    pid = serializers.SerializerMethodField()

    class Meta:
        model = DataBlock
        fields = ('id', 'slug', 'title', 'description', 'device', 'block', 'org', 'sg',
                  'created_on', 'created_by', 'pid', 'on_complete')
        read_only_fields = ('created_on', 'slug', 'created_by', 'block', 'sg',)
        extra_kwargs = {
            'on_complete': {'write_only': True, 'required': False},
        }

    def create(self, validated_data):
        on_complete = None
        if 'on_complete' in validated_data:
            # on_complete should be passed to the worker but it is not part of the dta block constructor
            on_complete = validated_data.pop('on_complete')
            logger.info('on_complete found: {}'.format(on_complete))
        else:
            logger.info('No on_complete found')

        device = self.validated_data['device']
        new_block_id = get_block_id(device)
        block = DataBlock(block=new_block_id, **validated_data)
        block.save()

        # Set device to Busy
        block.device.set_state('B0')
        block.device.save()

        # Schedule actual archive and store process ID
        # on_complete should be a JSON file representing how to change the device on completion
        self._pid = schedule_archive(block, on_complete)
        assert self._pid

        return block

    def get_pid(self, obj):
        if self._pid:
            return str(self._pid)
        return ''


class DataBlockUpdateSerializer(serializers.ModelSerializer):
    sg = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    org = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )

    class Meta:
        model = DataBlock
        fields = ('title', 'description', 'slug', 'block', 'org', 'sg', )
        read_only_fields = ('slug', 'org', 'block', 'sg', )


class DataBlockDataTableSerializer(serializers.ModelSerializer):
    slug = serializers.SerializerMethodField()
    device = serializers.SerializerMethodField()
    completed_on = serializers.SerializerMethodField()

    class Meta:
        model = DataBlock
        fields = ('slug', 'device', 'block', 'title', 'completed_on',)

    def get_slug(self, obj):
        return '<a href="{0}">{1}</a>'.format(obj.get_absolute_url(), obj.slug)

    def get_device(self, obj):
        return '<a href="{0}">{1}</a>'.format(obj.device.get_absolute_url(), obj.device.slug)

    def get_completed_on(self, obj):
        if obj.completed_on:
            return localtime(obj.completed_on).strftime('%Y/%m/%d %H:%M:%S')
        return 'Processing...'


class DataBlockExtraInfoSerializer(DataBlockSerializer):
    stream_counts = serializers.SerializerMethodField()

    class Meta:
        model = DataBlock
        fields = (
            'id',
            'slug',
            'title',
            'description',
            'created_on',
            'stream_counts'
        )
        read_only_fields = (
            'created_on',
            'slug',
        )

    def get_stream_counts(self, obj):
        distinct_data_streams = DataManager.filter_qs('data', device_slug=obj.slug).order_by('stream_slug').values('stream_slug').annotate(total=Count('id'))
        distinct_event_streams = DataManager.filter_qs('event', device_slug=obj.slug).order_by('stream_slug').values('stream_slug').annotate(total=Count('id'))

        stream_dict = {}

        for item in distinct_data_streams:
            stream_slug = item.pop('stream_slug')
            if 'total' in item:
                item['data_cnt'] = item.pop('total')
            if stream_slug in stream_dict:
                stream_dict[stream_slug].update(item)
            else:
                stream_dict[stream_slug] = item
            stream_dict[stream_slug]['has_streamid'] = False

        for item in distinct_event_streams:
            stream_slug = item.pop('stream_slug')
            if 'total' in item:
                item['event_cnt'] = item.pop('total')
            if stream_slug in stream_dict:
                stream_dict[stream_slug].update(item)
            else:
                stream_dict[stream_slug] = item
            stream_dict[stream_slug]['has_streamid'] = False

        for streamid in StreamId.objects.filter(block=obj):
            if streamid.slug in stream_dict:
                stream_dict[streamid.slug]['has_streamid'] = True

        return stream_dict
