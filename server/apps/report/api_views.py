import logging
import os
from django.shortcuts import get_object_or_404
from django.conf import settings

from rest_framework.views import APIView
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework import status
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied

from drf_yasg.utils import no_body, swagger_auto_schema
import django_filters

from apps.report.worker.report_generator import SummaryReportGeneratorAction
from apps.org.permissions import IsMemberOnly
from apps.org.models import Org
from apps.s3file.models import S3File
from apps.s3file.serializers import S3FileSerializer
from apps.s3file.utils import get_s3file_post_url, get_content_type
from apps.utils.aws.sqs import SqsPublisher

from .serializers import *
from .models import GeneratedUserReport
from .filters import GeneratedUserReportApiFilter

logger = logging.getLogger(__name__)


class APIReportSummaryGenerationViewSet(APIView):
    """
    Custom Login function.
    Returns user info and tokens if successful
    """
    permission_classes = (permissions.IsAuthenticated,)

    @swagger_auto_schema(
        operation_id='Report Summary - Generate',
        request_body=DeviceSummaryReportSerializer,
        responses={
            202: '{"status": "scheduled"}',
        }
    )
    def post(self, request, format=None):
        """
        Schedule a task to generate a Summary Report.
        Only a subset of reports (that do not require any configuration) can be generated with this function.
        The summary is emailed to the people in the notification_recipients list within a few minutes.

        notification_recipients is a list os strings of the form:

        - `email:<email>`  to send notification to any person (with our without an account)
        - `user:<username>` to send notification to a registered user
        - `org:admin` to send notification to all Org Admins
        - `org:all` to send notification to all members of the Org
        """
        data = JSONParser().parse(request)
        serializer = DeviceSummaryReportSerializer(data=data)

        if serializer.is_valid():

            rpt_payload = serializer.save(user=self.request.user)
            rpt_payload['attempt'] = 1
            SummaryReportGeneratorAction.schedule(args=rpt_payload)

            return Response({'status': 'scheduled'}, status=status.HTTP_202_ACCEPTED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class APIGeneratedUserReportViewSet(viewsets.ModelViewSet):
    """
    Get all Generated User Reports

    * Generated reports are static files that were generated at a given time for a given device or data block
    based on a configuration given by a predefined UserReport object

    """
    queryset = GeneratedUserReport.objects.none()
    serializer_class = GeneratedUserReportSerializer
    permission_classes = (IsMemberOnly,)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = GeneratedUserReportApiFilter

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        if self.request.user.is_staff and (self.request.GET.get('staff', '0') == '1'):
            qs = GeneratedUserReport.objects.all()
        else:
            orgs = Org.objects.user_orgs_ids(self.request.user, permission='can_access_reports')
            qs = GeneratedUserReport.objects.filter(org__in=orgs)

        return qs.select_related('org', 'created_by')

    def get_object(self):
        """
        Get object based on given uuid.

        Returns: object if it exists
        """
        obj = get_object_or_404(GeneratedUserReport, pk=self.kwargs['pk'])

        org = obj.org
        if org and not org.has_permission(self.request.user, 'can_access_reports'):
            raise PermissionDenied('No permission to access generated reports')

        return obj

    def perform_create(self, serializer):
        """
        Create new Generated Report object
        """
        org = serializer.validated_data['org']
        if not org.has_permission(self.request.user, 'can_create_reports'):
            raise PermissionDenied('User has no access permissions')

        generated_report = serializer.save(created_by=self.request.user)
        logger.info('Generated Report: {}'.format(generated_report))

    def perform_update(self, serializer):
        """
        Update Generated Report object
        """
        instance = self.get_object()
        org = instance.org
        if not org.has_permission(self.request.user, 'can_create_reports'):
            raise PermissionDenied('User has no access permissions')

        key = serializer.validated_data.get('key', None)
        s3file = None
        if key:
            # Create s3file
            s3file = instance.set_or_create_s3file(basename=key, user=self.request.user)

        generated_report = serializer.save(index_file=s3file)
        logger.info('Updated Generated Report: {}'.format(generated_report))

    @swagger_auto_schema(
        method='post',
        request_body=ReportAvailabilitySerializer,
        responses={
            202: 'Report availability',
        }
    )
    @action(methods=['post'], detail=False)
    def availability(self, request):
        """
        Check if the device or data block have any available reports.
        And if so, if the device/block have legal data to generate them.
        This API can be called to determine if a given report will be legal
        at the given time
        """
        serializer = ReportAvailabilitySerializer(data=request.data)
        if serializer.is_valid():
            report_worker_payload = serializer.save()

            return Response(report_worker_payload, status=status.HTTP_202_ACCEPTED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        method='post',
        request_body=ScheduleAnalyticsReportSerializer,
        responses={
            202: 'Request was accepted',
        }
    )
    @action(methods=['post'], detail=False)
    def schedule(self, request):
        """
        Schedule an Analytics Report
        """
        serializer = ScheduleAnalyticsReportSerializer(data=request.data)
        if serializer.is_valid():
            report_worker_payload = serializer.save(user=self.request.user)

            sqs = SqsPublisher(getattr(settings, 'SQS_ANALYTICS_QUEUE_NAME'))
            sqs.publish(payload=report_worker_payload)

            return Response(report_worker_payload, status=status.HTTP_202_ACCEPTED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        method='post',
        request_body=GeneratedUserReportS3FileUploadUrlSerializer,
        responses={
            202: '{"url": "url to use", "fields": "fields to upload on body", "uuid": "assigned to file"}',
        }
    )
    @action(methods=['post'], detail=True)
    def uploadurl(self, request, pk=None):
        """
        Generate URL and field data to be able to do a direct POST to S3 to upload a report file

        Use return payload to upload file like this:

            `requests.post(response["url"], data=response["fields"], files=files)`
        """
        serializer = GeneratedUserReportS3FileUploadUrlSerializer(data=request.data)
        if serializer.is_valid():
            name = serializer.data.get('name')
            acl = serializer.data.get('acl')
            content_type = serializer.data.get('content_type', None)

            instance = self.get_object()
            org = instance.org
            if not org.has_permission(self.request.user, 'can_create_reports'):
                raise PermissionDenied('User has no access permissions')

            key_template = getattr(settings, 'REPORTS_S3FILE_KEY_FORMAT')
            key_name = key_template.format(org=org.slug, uuid=str(instance.id), base=name)

            if not content_type:
                content_type = get_content_type(key_name)

            post = get_s3file_post_url(
                key_name=key_name,
                bucket=getattr(settings, 'REPORTS_S3FILE_BUCKET_NAME'),
                obj_uuid=str(instance.id),
                type='report',
                acl=acl,
                content_type=content_type,
                max_length=1024*5000 # 5M
            )
            post['uuid'] = str(instance.id)

            return Response(post, status=status.HTTP_202_ACCEPTED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        method='post',
        request_body=GeneratedUserReportS3FileSuccessUrlSerializer,
        responses={
            201: S3FileSerializer,
        }
    )
    @action(methods=['post'], detail=True)
    def uploadsuccess(self, request, pk=None):
        """
        Function should be called after a successful upload of a report file.
        """
        serializer = GeneratedUserReportS3FileSuccessUrlSerializer(data=request.data)
        if serializer.is_valid():
            name = serializer.data.get('name')

            instance = self.get_object()
            org = instance.org
            if not org.has_permission(self.request.user, 'can_create_reports'):
                raise PermissionDenied('User has no access permissions')

            s3file = instance.set_or_create_s3file(basename=name, user=self.request.user)

            if s3file:
                instance.index_file = s3file
                instance.status = 'G1'
                instance.save()

                # Send Notification to user
                instance.send_notifications()

                serializer = S3FileSerializer(s3file)

                return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
            else:
                return Response({'detail': 'Illegal or duplicate UUID'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

