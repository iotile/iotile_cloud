import json
import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404

import django_filters
from drf_yasg.utils import no_body, swagger_auto_schema
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.org.models import OrgMembership
from apps.property.mixins import GeneralPropertyMixin
from apps.utils.data_mask.api_helper import mask_api_helper
from apps.utils.data_mask.serializers import DeviceDataMaskSerializer
from apps.utils.rest.custom_serializers import MultiSerializerViewSetMixin

from .documents import *
from .models import *
from .serializers import *

logger = logging.getLogger(__name__)


# filterset_fields = ('created_by', 'project', 'org__slug', 'device__slug', 'variable')
class DataBlockFilter(django_filters.rest_framework.FilterSet):
    org = django_filters.CharFilter(method='filter_by_org')
    device = django_filters.CharFilter(method='filter_by_device')
    q = django_filters.CharFilter(method='search')
    class Meta:
        model = DataBlock
        fields = ['org', 'device']

    def filter_by_org(self, queryset, name, value):
        org = get_object_or_404(Org, slug=value)
        return queryset.filter(org=org)

    def filter_by_device(self, queryset, name, value):
        device = get_object_or_404(Device, slug=value)
        return queryset.filter(device=device)

    def search(self, queryset, name, value):
        org_slug = self.request.GET.get('org', None)
        if org_slug:
            s = DataBlockDocument.search()
            s = s.filter("term", org=org_slug)
            if value:
                s = s.query("multi_match", query=value, operator="and", type="cross_fields",
                    fields=[
                        'title',
                        'properties_val',
                        'description',
                        'slug',
                        'sensorgraph',
                        'notes',
                        'created_by',
                    ]
                )
            sqs = s.to_queryset()
            return sqs.order_by('created_by')
        raise ValidationError('Org argument (org=) is needed for search')


class APIDataBlockViewSet(MultiSerializerViewSetMixin, viewsets.ModelViewSet, GeneralPropertyMixin):
    """
    A DataBlock represents archived data for a given Device.
    It can be used for real archiving, or as a way to represent periods of time.
    For example, for a shipping application (logging data during a trip),
    DataBlocks can represent historical trips, allowing the user to clear the
    actual device data after each trip

    list: Get list of archives

    create: Schedule a new Archive

    """
    lookup_field = 'slug'
    queryset = DataBlock.objects.none()
    serializer_class = DataBlockSerializer
    serializer_action_classes = {
        'update': DataBlockUpdateSerializer,
        'partial_update': DataBlockUpdateSerializer,
    }
    permission_classes = (IsAuthenticated,)
    filterset_class = DataBlockFilter
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)

    def _user_blocks_qs(self, user):
        org_ids = OrgMembership.objects.filter(
            user=user,
            is_active=True,
            permissions__contains = {'can_access_datablock': True}
        ).values_list('org_id', flat=True)
        return DataBlock.objects.filter(org__in=org_ids).select_related('device', 'sg', 'org', 'created_by')

    def get_queryset(self):
        """
        This view should return a list of all records if staff
        or all records the user has access to if not
        """
        if self.request.user.is_staff and self.request.GET.get('staff', ''):
            return DataBlock.objects.all()

        return self._user_blocks_qs(self.request.user)

    def get_object(self):
        slug = self.kwargs['slug']

        block = get_object_or_404(DataBlock, slug=slug)

        if block.org.has_permission(self.request.user, 'can_access_datablock'):
            return block

        raise PermissionDenied

    def perform_create(self, serializer):
        device = serializer.validated_data['device']
        org = device.org
        if not device.has_access(self.request.user) or not org.has_permission(self.request.user, 'can_create_datablock'):
            raise PermissionDenied('No permission to create data blocks')

        if device.busy:
            raise PermissionDenied('Device is busy. Operation cannot be completed at this time')

        # 1. Create DataBlock object
        serializer.save(created_by=self.request.user, org=org)

    def destroy(self, request, *args, **kwargs):
        """
        Staff Only.
        Delete a Device. Not all users have delete permissions.
        """
        if not request.user.is_staff:
            return Response({'error': 'Restricted Access. Contact Arch'}, status=status.HTTP_403_FORBIDDEN)
        return super(APIDataBlockViewSet, self).destroy(request, *args)

    @action(methods=['get'], detail=False)
    def datatable(self, request):
        """
        Get data as a datatable
        """
        org = None
        start = 1
        length = 10
        cols = [
            'slug',
            'device',
            'block',
            'title',
            'completed_on'
        ]

        if 'length' in request.GET:
            length = int(request.GET['length'])

        if 'start' in request.GET:
            start = int(request.GET['start'])

        if 'device' in request.GET and request.GET['device']:
            device = get_object_or_404(Device, slug=self.request.GET['device'])
            org = device.org
            data = DataBlock.objects.filter(device=device, org=org)
        elif 'org' in request.GET and request.GET['org']:
            org = get_object_or_404(Org, slug=self.request.GET['org'])
            data = DataBlock.objects.filter(org=org)
        else:
            data = DataBlock.objects.none()

        if org and (not org.has_access(self.request.user) or not org.has_permission(self.request.user, 'can_access_datablock')):
            raise PermissionDenied('User has no permissions to datablocks')

        if 'search[value]' in request.GET and request.GET['search[value]']:
            q = request.GET['search[value]']
            if org:
                s = DataBlockDocument.search()
                s = s.filter("term", org=org.slug)
                if q:
                    s = s.query("multi_match", query=q, operator="and", type="cross_fields",
                        fields=[
                            'title',
                            'properties_val',
                            'description',
                            'slug',
                            'sensorgraph',
                            'created_by',
                            'notes',
                        ]
                    )
                data = s.to_queryset()

        ordered_by_field = 0
        if 'order[0][column]' in request.GET:
            ordered_by_field = int(request.GET['order[0][column]'])

        # logger.info('Sorted by {}'.format(ordered_by_field))
        order_by_str = cols[ordered_by_field]
        if 'order[0][dir]' in request.GET:
            sort_dir = request.GET['order[0][dir]']
            logger.debug('Sort Dir {}'.format(sort_dir))
            if sort_dir == 'desc':
                order_by_str = '-{0}'.format(cols[ordered_by_field])

        # logger.info('data will be sorted with order_by_str={0}'.format(order_by_str))
        data = data.order_by(order_by_str)

        if length == -1:
            logger.debug('length={0}, start={1}, Show ALL'.format(length, start))
            serializer = DataBlockDataTableSerializer(data, many=True)
        else:
            page_num = int(start / length) + 1
            logger.debug('length={0}, start={1}, page_num={2}'.format(length, start, page_num))
            p = Paginator(data, length)
            page = p.page(page_num)
            serializer = DataBlockDataTableSerializer(page.object_list, many=True)

        result = {}
        if 'sEcho' in request.GET:
            result['sEcho'] = int(request.GET['sEcho'])

        if 'draw' in request.GET:
            result["draw"] = request.GET['draw']
        result["recordsTotal"] = data.count()
        result["recordsFiltered"] = data.count()
        result["data"] = serializer.data

        return Response(result)

    @swagger_auto_schema(
        method='get',
        responses={
            200: DataBlockExtraInfoSerializer(many=False),
        }
    )
    @action(methods=['get'], detail=True)
    def extra(self, request, slug=None):
        """
        Get general information about this device, including
        the data counts per stream
        """
        obj = self.get_object()
        serializer = DataBlockExtraInfoSerializer(obj)
        return Response(serializer.data)

    @swagger_auto_schema(
        method='get',
        operation_description='Get current block data mask time ranges',
        responses={
            200: DeviceDataMaskSerializer(many=False),
            404: 'Data block slug not found'
        }
    )
    @swagger_auto_schema(
        method='patch',
        request_body=DeviceDataMaskSerializer,
        operation_description='Set time range for block data mask. All data outside range will be masked away (hidden). Datetime format in UTC. Example: `2018-01-01T01:00:00Z`',
        responses={
            202: DeviceDataMaskSerializer(many=False),
            404: 'Data block slug not found'
        }
    )
    @swagger_auto_schema(
        method='delete',
        responses={
            204: '',
        }
    )
    @action(methods=['get', 'delete', 'patch'], detail=True)
    def mask(self, request, slug=None):
        """
        DataBlock Data Mask API
        """
        block = self.get_object()
        return mask_api_helper(request=request, obj=block)




