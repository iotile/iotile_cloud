from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .mask_utils import clear_data_mask, get_data_mask_date_range, set_data_mask
from .serializers import DeviceDataMaskSerializer


def mask_api_helper(request, obj):
    """
    Device or DataBlock Data Mask API helper function
    (To share code between /device/slug/mask and /block/slug/mask
    """
    org = obj.org
    if request.method == 'GET':
        mask_data = get_data_mask_date_range(obj)
        if mask_data:
            serializer = DeviceDataMaskSerializer(mask_data)
        else:
            serializer = DeviceDataMaskSerializer({'start': None, 'end': None})
        return Response(serializer.data)

    elif request.method == 'PATCH':
        if org and org.has_permission(request.user, 'can_reset_device'):
            serializer = DeviceDataMaskSerializer(data=request.data)
            if serializer.is_valid():

                if obj.busy:
                    raise PermissionDenied('Device is busy. Operation cannot be completed at this time')

                start = serializer.data.get('start', None)
                end = serializer.data.get('end', None)
                event = set_data_mask(obj, start, end, [], [], user=request.user)

                return Response(event.extra_data, status=status.HTTP_202_ACCEPTED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            raise PermissionDenied
    elif request.method == 'DELETE':
        if org and org.has_permission(request.user, 'can_reset_device'):

            clear_data_mask(obj=obj, user=request.user)
            return Response({}, status=status.HTTP_204_NO_CONTENT)
        else:
            raise PermissionDenied

