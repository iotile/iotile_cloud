
from rest_framework import serializers

from .models import *


class S3FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = S3File
        fields = ('id', 'title', 'url', 'file_type', 'created_on', 'created_by')
        read_only_fields = ('created_on', 'created_by', 'file_type')

    def get_user_info(self, obj):
        user = obj.created_by
        return {
            'username': '@{}'.format(user.username),
            'slug': user.slug,
            'tiny_avatar': user.get_gravatar_tiny_url(),
        }


class S3FileUploadUrlSerializer(serializers.Serializer):
    """Use to get a POST uploadurl API"""
    name = serializers.CharField(required=True, help_text='Base filename of file to be uploaded (i.e. image.png)')


class S3FileSuccessUrlSerializer(serializers.Serializer):
    """Use to get a POST success API"""
    name = serializers.CharField(required=True, help_text='Base filename of file that was uploaded (i.e. image.png)')
    uuid = serializers.UUIDField(required=True, help_text='UUID returned by the uploadurl API')

