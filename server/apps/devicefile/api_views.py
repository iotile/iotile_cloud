import json
import os
import uuid

from django.core.exceptions import PermissionDenied

import django_filters
from drf_yasg.utils import no_body, swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.s3file.serializers import S3FileSerializer, S3FileSuccessUrlSerializer, S3FileUploadUrlSerializer
from apps.s3file.utils import get_s3file_post_url
from apps.utils.rest.permissions import IsStaffOrReadOnly

from .models import *
from .serializers import *


class DeviceFileFilter(django_filters.rest_framework.FilterSet):
    version = django_filters.CharFilter(method='image_version', required=False)
    class Meta:
        model = DeviceFile
        fields = ['version', 'type', 'tag']

    def image_version(self, queryset, name, value):

        elements = value.split('.')
        if len(elements):
            major = int(elements[0])
            queryset = queryset.filter(major_version=major)
        if len(elements) > 1:
            minor = int(elements[1])
            queryset = queryset.filter(minor_version=minor)

        return queryset


class APIDeviceFileViewSet(viewsets.ModelViewSet):
    """
    Not Documented. For Internal Use Only.
    """
    lookup_field = 'slug'
    queryset = DeviceFile.objects.none()
    serializer_class = DeviceFileSerializer
    permission_classes = (IsStaffOrReadOnly, )
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = DeviceFileFilter

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        if self.request.user.is_staff:
            return DeviceFile.objects.all()

        if 'slug' in self.kwargs:
            # Users are allowed to access if they know the ID
            return DeviceFile.objects.filter(released=True)

        # Users are not allowed to list all firmwares
        return DeviceFile.objects.none()

    def perform_create(self, serializer):
        # Include the owner attribute directly, rather than from request data.
        instance = serializer.save(created_by=self.request.user)

    @swagger_auto_schema(
        method='get',
        responses={
            200: DeviceS3FileSerializer,
        }
    )
    @action(methods=['get'], detail=True)
    def file(self, request, slug=None):
        """
        Return signed URL to download device file
        """
        obj = self.get_object()
        serializer = DeviceS3FileSerializer(obj)
        return Response(serializer.data)

    @swagger_auto_schema(
        method='post',
        request_body=S3FileUploadUrlSerializer,
        responses={
            202: '{"url": "url to use", "fields": "fields to upload on body", "uuid": "assigned to file"}',
        }
    )
    @action(methods=['post'], detail=True)
    def uploadurl(self, request, slug=None):
        """
        Generate URL and field data to be able to do a direct POST to S3 to upload a device file

        Use return payload to upload file like this:

            `requests.post(response["url"], data=response["fields"], files=files)`
        """
        serializer = S3FileUploadUrlSerializer(data=request.data)
        if serializer.is_valid():
            name = serializer.data.get('name')
            file_uuid = str(uuid.uuid4())

            obj = self.get_object()
            if not self.request.user.is_staff:
                raise PermissionDenied('Not allowed to upload to {0}'.format(obj.slug))

            key_name = os.path.join(settings.S3FILE_INCOMING_KEYPATH, 'script', file_uuid, name)

            post = get_s3file_post_url(
                key_name=key_name,
                obj_uuid=file_uuid,
                type='script',
                max_length=1024000
            )
            post['uuid'] = file_uuid

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
    def uploadsuccess(self, request, slug=None):
        """
        Function should be called after a successful upload of a device file.
        """
        serializer = S3FileSuccessUrlSerializer(data=request.data)
        if serializer.is_valid():
            name = serializer.data.get('name')
            file_uuid = serializer.data.get('uuid')

            obj = self.get_object()
            if not self.request.user.is_staff:
                raise PermissionDenied('Not allowed to upload to {0}'.format(obj.slug))

            key_name = os.path.join(settings.S3FILE_INCOMING_KEYPATH, 'script', file_uuid, name)

            s3file = S3File.objects.create_file(uuid=file_uuid, name=name, key=key_name, user=request.user)

            if s3file:
                obj.file = s3file
                obj.save()

                serializer = S3FileSerializer(s3file)

                return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
            else:
                return Response({'detail': 'Illegal or duplicate UUID'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


