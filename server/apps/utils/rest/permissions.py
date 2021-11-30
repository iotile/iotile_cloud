__author__ = 'dkarchmer'

from rest_framework_api_key.permissions import BaseHasAPIKey

from rest_framework import permissions

from apps.org.models import AuthAPIKey
from apps.utils.api_key_utils import get_apikey_object_from_generated_key


class IsOwnerOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to access (read/write)
    """

    def has_permission(self, request, view):

        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):

        # Write permissions are only allowed to the owner of the snippet
        return obj is None or obj.created_by == request.user


class IsStaffOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to access (read/write)
    """

    def has_permission(self, request, view):

        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        return request.user.is_staff

    def has_object_permission(self, request, view, obj):

        if request.method in permissions.SAFE_METHODS:
            # Check permissions for read-only request
            return request.user.is_authenticated
        else:
            # Check permissions for write request
            return request.user.is_staff


class ReadOnly(permissions.BasePermission):
    """
    Custom permission to allow only read access
    """

    def has_permission(self, request, view):

        return request.method in permissions.SAFE_METHODS


class HasAuthAPIKey(BaseHasAPIKey):
    model = AuthAPIKey

    def get_key_from_request(self, request):
        apikey = self.get_key(request)
        return get_apikey_object_from_generated_key(apikey)

    def has_permission(self, request, view):
        actualKey = self.get_key_from_request(request)
        if actualKey is None:
            return False
        return True

    def has_object_permission(self, request, view, obj):
        actualKey = self.get_key_from_request(request)
        if actualKey is None:
            return False
        if actualKey.org.slug is not obj.slug:
            return False
        return self.has_permission(request, view)

class HasAuthAPIKeyNoOrg(HasAuthAPIKey):

    def has_object_permission(self, request, view, obj):
        actualKey = self.get_key_from_request(request)
        if actualKey is None:
            return False
        return self.has_permission(request, view)
