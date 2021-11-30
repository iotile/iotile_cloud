
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .pid import ActionPID
from .serializers import *


class APIActionPidViewSet(APIView):
    """
    View Server Info
    """
    permission_classes = (IsAuthenticated, )

    def post(self, request, format=None):
        """
        Check on a backend worker action process ID
        """
        data = JSONParser().parse(request)
        serializer = ActionPidSerializer(data=data)

        if not serializer.is_valid():
            Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
