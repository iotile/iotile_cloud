import json
import logging

from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer

from apps.utils.fineuploader.serializers import FineUploaderSignSerializer
from apps.utils.aws.s3 import sign_policy_document, sign_headers

from .models import S3File

logger = logging.getLogger(__name__)


class APIFineUploaderSignViewSet(APIView):
    """
    API to
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = FineUploaderSignSerializer

    private_key = settings.S3FILE_PRIVATE_KEY
    bucket_name = settings.S3FILE_BUCKET_NAME
    max_size = settings.S3FILE_MAX_SIZE

    def _is_valid_policy(self, conditions):
        """ Verify the policy document has not been tampered with client-side
        before sending it off.
        """
        bucket = ''
        parsed_max_size = 0

        for condition in conditions:
            # print('Checking condition: ' + str(condition))
            if isinstance(condition, list) and condition[0] == 'content-length-range':
                parsed_max_size = condition[2]
            else:
                if condition.get('bucket', None):
                    bucket = condition['bucket']

        policy1 = (bucket == self.bucket_name)
        policy2 = (int(parsed_max_size) == int(self.max_size))
        result = policy1 and policy2
        if (not result):
            logger.info('is valid policy1 = ' + str(policy1))
            logger.info('----> bucket(%s) == settings.bucket(%s)' % (bucket, self.bucket_name))
            logger.info('is valid policy2 = ' + str(policy2))
            logger.info(
                '----> parsed_max_size(%s) == settings.max(%s)' % (parsed_max_size, self.max_size))
            logger.error('is valid policy = ' + str(result))
        return result

    def post(self, request, format=None):
        """ This is where the upload will send a POST request after the
        file has been stored in S3.
        """
        data = JSONParser().parse(request)
        # print(data)
        serializer = FineUploaderSignSerializer(data=data)

        if serializer.is_valid():
            expiration = serializer.data.get('expiration')
            conditions = serializer.data.get('conditions')

            # print(expiration)
            # print(conditions)

            request_payload = data
            # print(request_payload)
            logger.debug('Request Payload: ' + str(request_payload))
            headers = request_payload.get('headers', None)
            if headers:
                # The presence of the 'headers' property in the request payload
                # means this is a request to sign a REST/multipart request
                # and NOT a policy document
                response_data = sign_headers(headers, self.private_key)
            else:
                if not self._is_valid_policy(conditions):
                    logger.error('Invalid Policy')
                    return Response({'invalid': True}, status=status.HTTP_400_BAD_REQUEST)
                response_data = sign_policy_document(request_payload, self.private_key)

            # print(response_data)
            return Response(response_data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
