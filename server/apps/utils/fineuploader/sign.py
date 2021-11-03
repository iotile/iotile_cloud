import json
import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View

from apps.utils.aws.s3 import sign_policy_document, sign_headers

# Get an instance of a logger
logger = logging.getLogger(__name__)

class FineUploaderSignMixIn(object):
    http_method_names = ['post',]
    private_key = ''
    bucket_name = ''
    max_size = 1

    def make_response(self, status=200, content=None):
        """ Construct an HTTP response. Fine Uploader expects 'application/json'.
        """
        response = HttpResponse()
        response.status_code = status
        response['Content-Type'] = "application/json"
        response.content = content
        return response

    def is_valid_policy(self, policy_document):
        """ Verify the policy document has not been tampered with client-side
        before sending it off.
        """
        bucket = ''
        parsed_max_size = 0

        logger.debug(str(policy_document['conditions']))

        for condition in policy_document['conditions']:
            #print('Checking condition: ' + str(condition))
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

    def post(self, request, *args, **kwargs):
        """ Handle S3 uploader POST requests here. For files <=5MiB this is a simple
        request to sign the policy document. For files >5MiB this is a request
        to sign the headers to start a multipart encoded request.
        """

        if request.POST.get('success', None):
            return self.make_response(200)
        else:
            request_payload = json.loads(request.body.decode())
            logger.debug('Request Payload: ' + str(request_payload))
            headers = request_payload.get('headers', None)
            if headers:
                # The presence of the 'headers' property in the request payload
                # means this is a request to sign a REST/multipart request
                # and NOT a policy document
                response_data = sign_headers(headers, self.private_key)
            else:
                if not self.is_valid_policy(request_payload):
                    logger.error('Invalid Policy')
                    return self.make_response(400, {'invalid': True})
                response_data = sign_policy_document(request_payload, self.private_key)
            response_payload = json.dumps(response_data)
            #print(str(response_data))

            return self.make_response(200, response_payload)

    @method_decorator(login_required)
    @csrf_exempt
    def dispatch(self, request, *args, **kwargs):
        return super(FineUploaderSignMixIn, self).dispatch(request, *args, **kwargs)



