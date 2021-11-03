
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied

from drf_yasg.utils import swagger_auto_schema

from .serializers import *

class GeneralPropertyMixin(object):

    @swagger_auto_schema(
        method='get',
        responses={
            200: TargetPropertyReadOnlySerializer(many=True),
        }
    )
    @action(methods=['get'], detail=True)
    def properties(self, request, slug=None, pk=None):
        """
        Get user properties associated to a device
        """
        # Need to call get_object to get access checks
        obj = self.get_object()

        org = obj.org
        if not self.request.user.is_staff:
            if org and not org.has_permission(self.request.user, 'can_read_device_properties'):
                raise PermissionDenied('User has no access to read properties')

        if slug:
            qs = GenericProperty.objects.filter(target=slug)
        else:
            qs = obj.get_properties_qs()

        serializer = TargetPropertyReadOnlySerializer(qs, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        method='post',
        request_body=PostPropertySerializer,
        responses={
            201: TargetPropertyReadOnlySerializer(),
        }
    )
    @action(methods=['post'], detail=True)
    def new_property(self, request, slug=None, pk=None):
        """
        Create new Device Property.

        Payload is either
        1. `name` and `int_value` for an integer property
        1. `name` and `str_value` for a string property
        1. `name` and `bool_value` for a boolean property
        """
        # Need to call get_object to get access checks
        obj = self.get_object()
        if not slug:
            slug = obj.slug

        org = obj.org
        if not self.request.user.is_staff:
            if org and not org.has_permission(self.request.user, 'can_modify_device_properties'):
                raise PermissionDenied('User has no access to create/modify properties')

        serializer = PostPropertySerializer(data=request.data)
        if serializer.is_valid():
            prop = None
            target = slug
            name = serializer.validated_data['name']
            is_system = serializer.validated_data['is_system']

            type_count = int('int_value' in serializer.validated_data)
            type_count += int('str_value' in serializer.validated_data)
            type_count += int('bool_value' in serializer.validated_data)
            if type_count != 1:
                return Response('Only one of int_value,str_value,bool_value can be used',
                                status=status.HTTP_400_BAD_REQUEST)

            # If there is already a property with this name for this target, replace with new one
            try:
                prop = GenericProperty.objects.get(target=target, name=name)
                prop.created_by = request.user
                if 'int_value' in serializer.validated_data:
                    prop.set_int_value(serializer.validated_data['int_value'])
                if 'str_value' in serializer.validated_data:
                    prop.set_str_value(serializer.validated_data['str_value'])
                if 'bool_value' in serializer.validated_data:
                    prop.set_bool_value(serializer.validated_data['bool_value'])
                prop.save()
            except GenericProperty.DoesNotExist:
                if 'int_value' in serializer.validated_data:
                    v = serializer.validated_data['int_value']
                    prop = GenericProperty.objects.create_int_property(slug=target, name=name, value=v,
                                                                       is_system=is_system, created_by=request.user)
                if 'str_value' in serializer.validated_data:
                    v = serializer.validated_data['str_value']
                    prop = GenericProperty.objects.create_str_property(slug=target, name=name, value=v,
                                                                       is_system=is_system, created_by=request.user)
                if 'bool_value' in serializer.validated_data:
                    v = serializer.validated_data['bool_value']
                    prop = GenericProperty.objects.create_bool_property(slug=target, name=name, value=v,
                                                                        is_system=is_system, created_by=request.user)

            if prop:
                result_serializer = TargetPropertyReadOnlySerializer(prop)
                return Response(result_serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

