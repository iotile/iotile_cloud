import logging
import os
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

import django_filters
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.s3file.models import S3File
from apps.s3file.serializers import S3FileSerializer, S3FileSuccessUrlSerializer, S3FileUploadUrlSerializer
from apps.s3file.utils import get_s3file_post_url
from apps.utils.rest.pagination import LargeResultsSetPagination

from .helpers import StreamNoteBuilderHelper
from .models import StreamNote
from .serializers import StreamNoteSerializer

user_model = get_user_model()

# Get an instance of a logger
logger = logging.getLogger(__name__)


class StreamNoteFilter(django_filters.rest_framework.FilterSet):
    target = django_filters.CharFilter(field_name='target_slug', required=True)
    # Datetime format in UTC: `2018-01-01T01:00:00Z`
    start = django_filters.IsoDateTimeFilter(field_name='timestamp', lookup_expr='gte')
    # Datetime format in UTC: `2018-01-01T01:00:00Z`
    end = django_filters.IsoDateTimeFilter(field_name='timestamp', lookup_expr='lt')
    id = django_filters.RangeFilter(field_name='id')
    lastn = django_filters.NumberFilter(method='get_lastn')
    class Meta:
        model = StreamNote
        fields = ['target', 'timestamp']

    def get_lastn(self, queryset, name, value):
        if value < 1:
            raise ValidationError('lastn must be greater than 0')
        elif value > 100000:
            raise ValidationError('lastn limit is 100000')

        n = queryset.count()
        if value > n:
            # queryset doesn't support negative indexing
            qs = queryset.order_by('timestamp')
        else:
            qs = queryset.order_by('timestamp')[n-value:]

        return qs


class APIStreamNoteViewSet(viewsets.ModelViewSet):
    """
    Get all Stream Annotations.

    * StreamNote is a time based note

    This API requires a filter argument, in the form of:

    * `/api/v1/note/?target=d--0000-0000-0000-aaaa`  to show all notes for a given device
    * `/api/v1/note/?target=s--0000-0001--0000-0000-0000-aaaa--5001`  to show all notes for a given stream

    create: Staff Only.
    destroy: Staff Ony.
    destroy: Staff Only.

    """
    queryset = StreamNote.objects.all().select_related('created_by').prefetch_related('attachment')
    serializer_class = StreamNoteSerializer
    permission_classes = (IsAuthenticated,)
    pagination_class = LargeResultsSetPagination
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = StreamNoteFilter

    def get_object(self):
        """
        Get object if Staff

        """
        try:
            pk = int(self.kwargs['pk'])
        except Exception as e:
            raise ValidationError('Note ID must be a integer')

        note = get_object_or_404(StreamNote, pk=pk)

        if self.request.user.is_staff:
            return note

        target = note.target
        org = target.org
        if org.has_access(self.request.user):
            return note

        raise PermissionDenied

    def perform_create(self, serializer):
        helper = StreamNoteBuilderHelper()
        entries = []
        many = isinstance(serializer.validated_data, list)

        if many:
            count = 0
            for item in serializer.validated_data:
                note = helper.process_serializer_data(self.request, item)
                if note and helper.user_has_write_access(note=note, user=self.request.user):
                    entries.append(note)
                    count += 1
                else:
                    if note:
                        raise PermissionDenied('Not allowed to upload to {0}'.format(note.target_slug))
                    raise PermissionDenied('Stream not enabled {0}'.format(item['stream_slug']))
            logger.info('Committing batch of {0} data note entries'.format(count))
            if count:
                StreamNote.objects.bulk_create(entries)
                return {'count': count}
        else:
            note = helper.process_serializer_data(self.request, serializer.validated_data)
            if note and helper.user_has_write_access(note=note, user=self.request.user):
                note.save()
                result = StreamNoteSerializer(note)
                return result.data
            else:
                raise PermissionDenied('Not allowed to upload to {0}'.format(note.target_slug))

    @swagger_auto_schema(
        request_body=StreamNoteSerializer,
        responses={
            201: StreamNoteSerializer,
        }
    )
    def create(self, request, *args, **kwargs):
        many = isinstance(request.data, list)
        serializer = self.get_serializer(data=request.data, many=many)
        serializer.is_valid(raise_exception=True)
        data = self.perform_create(serializer)
        return Response(data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj:
            target = obj.target
            org = target.org
            if org.has_permission(self.request.user, 'can_read_notes'):
                return super(APIStreamNoteViewSet, self).retrieve(request, *args, **kwargs)

        raise PermissionDenied('Not allowed to read note')

    @swagger_auto_schema(
        method='post',
        request_body=S3FileUploadUrlSerializer,
        responses={
            202: '{"url": "url to use", "fields": "fields to upload on body", "uuid": "assigned to file"}',
        }
    )
    @action(methods=['post'], detail=True)
    def uploadurl(self, request, pk=None):
        """
        Generate URL and field data to be able to do a direct POST to S3 to upload a note attachment.

        Use return payload to upload file like this:

            `requests.post(response["url"], data=response["fields"], files=files)`
        """
        serializer = S3FileUploadUrlSerializer(data=request.data)
        if serializer.is_valid():
            name = serializer.data.get('name')
            file_uuid = uuid.uuid4()

            obj = self.get_object()
            if not obj:
                raise PermissionDenied('Not allowed to upload to {0}'.format(obj.target_slug))

            key_name = os.path.join(settings.S3FILE_INCOMING_KEYPATH, 'note', str(file_uuid), name)

            post = get_s3file_post_url(
                key_name=key_name,
                obj_uuid=str(file_uuid),
                type='note',
                max_length=4096000
            )
            post['uuid'] = str(file_uuid)

            return Response(post, status=status.HTTP_202_ACCEPTED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        method='post',
        request_body=S3FileSuccessUrlSerializer,
        responses={
            201: S3FileSerializer,
        }
    )
    @action(methods=['post'], detail=True)
    def uploadsuccess(self, request, pk=None):
        """
        Function should be called after a successful upload of a note attachment.
        """
        serializer = S3FileSuccessUrlSerializer(data=request.data)
        if serializer.is_valid():
            name = serializer.data.get('name')
            file_uuid = serializer.data.get('uuid')

            obj = self.get_object()
            if not obj:
                raise PermissionDenied('Not allowed to upload to {0}'.format(obj.target_slug))

            key_name = os.path.join(settings.S3FILE_INCOMING_KEYPATH, 'note', file_uuid, name)

            s3file = S3File.objects.create_file(uuid=file_uuid, name=name, key=key_name, user=request.user)

            if s3file:
                obj.attachment = s3file
                obj.save()

                serializer = S3FileSerializer(s3file)

                return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
            else:
                return Response({'detail': 'Illegal or duplicate UUID'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
