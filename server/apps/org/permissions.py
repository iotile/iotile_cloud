from rest_framework import permissions


class IsMemberOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to access (read/write)
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return obj is None or request.user.is_staff or obj.has_access(user=request.user)