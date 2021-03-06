import json

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse

from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.staff.serializers import DbStatsSerializer

from .serializers import *


class APIServerInfoViewSet(APIView):
    """
    View Server Info
    """

    def get(self, request, format=None):
        """
        Get Basic Server Information
        """
        serializer = ServerInfoSerializer(self.request)
        return Response(serializer.data, status=status.HTTP_200_OK)


class APIDbStatsViewSet(APIView):
    """
    View Server Info
    """
    permission_classes = (IsAdminUser, )

    def get(self, request, format=None):
        """
        Get Basic Server Information
        """
        serializer = DbStatsSerializer(self.request)
        return Response(serializer.data, status=status.HTTP_200_OK)
