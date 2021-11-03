from rest_framework.exceptions import APIException


class ApiIllegalFilterOrTargetException(APIException):
    status_code = 400
    default_detail = 'Bad Request: Illegal filter/target string'
    default_code = 'bad_request'


class ApiIllegalSlugException(APIException):
    status_code = 400
    default_detail = 'Bad Request: Illegal Project, Device or Stream slug'
    default_code = 'bad_request'


class ApiIllegalPkException(APIException):
    status_code = 400
    default_detail = 'Bad Request: Expected an integer database ID'
    default_code = 'bad_request'


