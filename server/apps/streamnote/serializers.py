import logging
from rest_framework import serializers

from apps.s3file.serializers import S3FileSerializer
from .models import StreamNote

# Get an instance of a logger
logger = logging.getLogger(__name__)


class StreamNoteSerializer(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField()
    target = serializers.CharField(source='target_slug', required=True)
    timestamp = serializers.DateTimeField()
    attachment = S3FileSerializer(read_only=True)
    class Meta:
        model = StreamNote
        fields = ('id', 'target', 'timestamp', 'note', 'type', 'user_info', 'attachment')
        read_only_fields = ('created_on', 'created_by', 'type')

    def get_user_info(self, obj):
        user = obj.created_by
        return {
            'username': '@{}'.format(user.username),
            'slug': user.slug,
            'tiny_avatar': user.get_gravatar_tiny_url(),
        }
