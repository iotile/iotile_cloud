from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from rest_framework import serializers

from iotile_cloud.utils.gid import IOTileDeviceSlug, IOTileBlockSlug

from apps.physicaldevice.models import Device
from apps.utils.rest.exceptions import ApiIllegalSlugException
from apps.s3file.serializers import S3FileSerializer, S3FileUploadUrlSerializer
from apps.org.models import Org
from apps.utils.objects.utils import get_object_by_slug
from apps.verticals.utils import get_analytics_report_availability_vertical_helper

from .models import GeneratedUserReport
from .generator.analytics.choices import template_choices


class DeviceSummaryReportSerializer(serializers.Serializer):
    device_slug = serializers.CharField(
        max_length=22, required=False,
        help_text='Format: "d--0000-0000-0000-0001"'
    )
    slug = serializers.CharField(
        max_length=22, required=False,
        help_text='Device or Datablock (archive) to generate report for. Format: "d--0000-0000-0000-0001" or "b--0011-0000-0000-0001"'
    )
    notification_recipients = serializers.ListField(child = serializers.CharField(max_length=64))
    generator = serializers.ChoiceField(choices=[
        ('end_of_trip', 'Shipping - End of Trip'),
    ])

    def create(self, validated_data):
        if 'slug' in validated_data and 'device_slug' in validated_data:
            raise ApiIllegalSlugException('slug and device_slug cannot be used together. Use slug')

        if 'slug' in validated_data:
            raw_slug = validated_data.get('slug')
            if raw_slug[0] == 'd':
                slug_class = IOTileDeviceSlug
            elif raw_slug[0] == 'b':
                slug_class = IOTileBlockSlug
            else:
                raise ApiIllegalSlugException('Illegal device or datablock slug: {}'.format(validated_data.get('slug')))

            try:
                obj_slug = slug_class(raw_slug)
            except ValueError:
                raise ApiIllegalSlugException('Illegal device slug: {}'.format(validated_data.get('device_slug')))

        elif 'device_slug' in validated_data:
            try:
                obj_slug = IOTileDeviceSlug(validated_data.get('device_slug'))
            except ValueError:
                raise ApiIllegalSlugException('Illegal device slug: {}'.format(validated_data.get('device_slug')))
        else:
            raise ApiIllegalSlugException('Missing slug')

        generator = validated_data.get('generator')
        notification_recipients = validated_data.get('notification_recipients')

        user = validated_data.get('user')

        _, obj = get_object_by_slug(str(obj_slug))
        if not obj or not obj.has_access(user):
            raise PermissionDenied('User has no access to device')

        return {
            'generator': generator,
            'notification_recipients': notification_recipients,
            'sources': [str(obj_slug), ],
            'org': obj.org.slug,
            'user': user.slug,
            'config': {}
        }


class ScheduleAnalyticsReportSerializer(serializers.Serializer):
    report = serializers.CharField(required=False, max_length=50, help_text='ID of optional User Report')
    label = serializers.CharField(max_length=50, help_text='Report Label', required=False)
    slug = serializers.CharField(max_length=22, help_text='Format: "d--0000-0000-0000-0001"')
    template = serializers.ChoiceField(choices=template_choices)
    args = serializers.JSONField(required=False)

    def create(self, validated_data):
        raw_slug = validated_data.get('slug')
        if raw_slug[0] == 'd':
            slug_class = IOTileDeviceSlug
        elif raw_slug[0] == 'b':
            slug_class = IOTileBlockSlug
        else:
            raise ApiIllegalSlugException('Illegal device or datablock slug: {}'.format(validated_data.get('slug')))

        try:
            obj_slug = slug_class(raw_slug)
        except ValueError:
            raise ApiIllegalSlugException('Illegal device or datablock slug: {}'.format(validated_data.get('slug')))

        template = validated_data.get('template')
        args = validated_data.get('args')
        user = validated_data.get('user')

        _, obj = get_object_by_slug(str(obj_slug))

        if not obj or not obj.org.has_permission(user, 'can_create_reports'):
            raise PermissionDenied('User has no access to object')

        label = validated_data.get('label', None)
        if not label:
            label = '{}: {}'.format(template, str(obj_slug))

        # Create a GenereatedReport here, so it is easier to report status and errors later
        generated_report_id = validated_data.get('report', None)
        if not generated_report_id:
            generated_report = GeneratedUserReport.objects.create(
                status='GS',
                label=label,
                source_ref=str(obj_slug),
                org=obj.org,
                created_by=user
            )
            generated_report_id = str(generated_report.id)

        return {
            'report': generated_report_id,
            'template': template,
            'group_slug': str(obj_slug),
            'user': user.email,
            'token': user.jwt_token,
            'args': args
        }


class GeneratedUserReportSerializer(serializers.ModelSerializer):
    created_by = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    org = serializers.SlugRelatedField(
        queryset = Org.objects.all(),
        slug_field = 'slug',
        required = True
    )
    index_file = S3FileSerializer(read_only=True)
    user_info = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()
    key = serializers.CharField(write_only=True, required=False)
    class Meta:
        model = GeneratedUserReport
        fields = ('id', 'label', 'source_ref', 'user_info', 'url', 'report', 'created_on', 'created_by', 'org', 'index_file', 'status', 'key')
        read_only_fields = ('created_on', 'created_by')

    def get_user_info(self, obj):
        user = obj.created_by
        return {
            'username': '@{}'.format(user.username),
            'slug': user.slug,
            'tiny_avatar': user.get_gravatar_tiny_url(),
        }

    def get_url(self, obj):
        return None


class GeneratedUserReportS3FileUploadUrlSerializer(S3FileUploadUrlSerializer):
    acl = serializers.ChoiceField(
        required=False,
        default='private',
        choices=[
            ('public-read', 'Public'),
            ('private', 'Private'),
        ],
        help_text='index file should be private while associated files should be public-read'
    )
    content_type = serializers.ChoiceField(
        required=False,
        choices=[
            ('text/plain', 'Plain'),
            ('text/html', 'HTML'),
            ('text/csv', 'CSV'),
            ('image/png', 'PNG'),
            ('image/jpeg', 'JPG'),
            ('application/zip', 'ZIP'),
            ('application/javascript', 'js/Jsonp'),
            ('application/json', 'Json'),
            ('application/octet-stream', 'Binary'),
        ],
        help_text='Content-Type for file to upload. Defaults to auto detection based on extension'
    )


class GeneratedUserReportS3FileSuccessUrlSerializer(serializers.Serializer):
    """Use to get a POST success API"""
    name = serializers.CharField(required=True, help_text='Base filename of report index that was uploaded (i.e. index.html)')


class ReportAvailabilitySerializer(serializers.Serializer):
    """Use to ask cloud if device is able to generate analytics reports"""
    slug = serializers.CharField(max_length=22, help_text='Format: "d--0000-0000-0000-0001"', required=True)

    def create(self, validated_data):
        raw_slug = validated_data.get('slug')
        if raw_slug[0] == 'd':
            slug_class = IOTileDeviceSlug
        elif raw_slug[0] == 'b':
            slug_class = IOTileBlockSlug
        else:
            raise ApiIllegalSlugException('Illegal device slug: {}'.format(validated_data.get('device_slug')))

        try:
            obj_slug = slug_class(raw_slug)
        except ValueError:
            raise ApiIllegalSlugException('Illegal device slug: {}'.format(validated_data.get('device_slug')))

        name, obj = get_object_by_slug(str(obj_slug))

        # Get Application Specific availability
        helper = get_analytics_report_availability_vertical_helper(obj)
        return helper.get_availability_payload()



