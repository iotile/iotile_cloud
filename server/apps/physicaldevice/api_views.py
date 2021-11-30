from django.core.exceptions import PermissionDenied

import django_filters
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from iotile_cloud.utils.gid import IOTileProjectSlug

from apps.deviceauth.authentication import DEVICE_TOKEN_AUTH_HEADER_PREFIX, encode_device_ajwt_key
from apps.deviceauth.models import DeviceKey
from apps.devicetemplate.serializers import DeviceTemplateSerializer
from apps.org.permissions import IsMemberOnly
from apps.ota.models import DeviceVersionAttribute
from apps.ota.serializers import DeviceVersionAttributeReadOnlySerializer
from apps.property.mixins import GeneralPropertyMixin
from apps.sensorgraph.serializers import SensorGraphSerializer
from apps.streamer.serializers import StreamerSerializer
from apps.utils.api_key_utils import get_org_slug_from_apikey
from apps.utils.data_mask.api_helper import mask_api_helper
from apps.utils.data_mask.serializers import DeviceDataMaskSerializer
from apps.utils.rest.pagination import LargeResultsSetPagination
from apps.utils.rest.permissions import HasAuthAPIKey, ReadOnly
from apps.utils.uuid_utils import validate_uuid

from .claim_utils import device_claim
from .serializers import *
from .tasks import schedule_reset, send_device_action_notification
from .worker.device_data_trim import DeviceDataTrimAction
from .worker.device_unclaim import DeviceUnClaimAction


class DeviceApiFilter(django_filters.rest_framework.FilterSet):
    project = django_filters.CharFilter(method='filter_by_project')
    dt = django_filters.CharFilter(method='filter_by_dt', label='Device Template')
    sg = django_filters.CharFilter(method='filter_by_sg', label='Sensor Graph')
    external_id = django_filters.CharFilter(method='filter_by_external_id', label='External ID')
    claimed = django_filters.BooleanFilter(method='filter_by_claimed', label='Claimed')
    property = django_filters.CharFilter(method='filter_by_property')

    class Meta:
        model = Device
        fields = ['dt', 'sg', 'claimed', 'external_id', 'project', 'org__slug']

    def filter_by_project(self, queryset, name, value):
        # Filter by project using either UUID or Slug
        if not validate_uuid(value):
            try:
                project_slug = IOTileProjectSlug(value)
                return queryset.filter(project__slug=str(project_slug))
            except Exception:
                return queryset.none()

        return queryset.filter(project_id=value)

    def filter_by_dt(self, queryset, name, value):
        dt = get_object_or_404(DeviceTemplate, slug=value)
        return queryset.filter(template=dt)

    def filter_by_sg(self, queryset, name, value):
        sg = get_object_or_404(SensorGraph, slug=value)
        return queryset.filter(sg=sg)

    def filter_by_external_id(self, queryset, name, value):
        return queryset.filter(external_id=value)

    def filter_by_claimed(self, queryset, name, value):
        return queryset.exclude(project__isnull=True)

    def filter_by_property(self, queryset, name, value):
        parts = value.split('__')
        if len(parts) == 1:
            properties = GenericProperty.objects.filter(target__istartswith='p--', name=parts[0])
            slugs = [p.target for p in properties]
            return queryset.filter(slug__in=slugs)
        if len(parts) == 2:
            properties = GenericProperty.objects.filter(target__istartswith='p--', name=parts[0], str_value=parts[1])
            slugs = [p.target for p in properties]
            return queryset.filter(slug__in=slugs)
        return queryset


class APIDeviceViewSet(viewsets.ModelViewSet, GeneralPropertyMixin):
    """
    API to get IOTile Device Information
    
    Get all Devices that the authenticated user has access to. 
    
    A Device represents a single physical IOTile device with a unique universal ID. 
    The `slug` is an representation of this ID in HEX form and using a format like `d--0000-0000-0000-000`
     
    Devices are configured with a SensorGraph, which represents the device application configuration. A Water Meter
    is configured with a Water Meter Sensor Graph which tells the device which information to send to the cloud

    Devices can be claimed and unclaimed by users, and tracked by a Project.
    
    list: Get list of devices that the user has access to
    
    create: Staff Only. Devices cannot be created by User
    """
    lookup_field = 'slug'
    queryset = Device.objects.none()
    # TODO: Change back to StandardResultsSetPagination (just remove to get default)
    pagination_class = LargeResultsSetPagination
    permission_classes = (IsMemberOnly,)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = DeviceApiFilter

    def get_serializer_class(self):
        if self.request.user.is_staff and (self.request.GET.get('staff', '0') == '1'):
            return DeviceSerializer
        return DeviceUserSerializer

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        all = (self.request.GET.get('all', '0') == '1')
        if self.request.user.is_staff and (self.request.GET.get('staff', '0') == '1'):
            qs = Device.objects.all()
        else:
            qs = Device.objects.user_device_qs(self.request.user, all=all)

        return qs.select_related('org', 'project', 'template', 'sg', 'claimed_by')

    def get_object(self):
        """
        Get object based on given slug. prepend '0000' as needed to
        properly format the device gid='d--0000-0000-0000-0001'

        Returns: Device if it exist

        """
        slug = self.kwargs['slug']

        # TODO: Should we only allow access to the device in question when using a-jwt?
        if self.request.auth and isinstance(self.request.auth, dict):
            if 'device' in self.request.auth:
                jwt_device = self.request.auth['device']
                if jwt_device != slug:
                    logger.warning('a-jwt for device {0} accessing device {1}'.format(jwt_device, slug))

        slug_elements = slug.split('--')
        if len(slug_elements) == 2 and slug_elements[0] in ['d', 'b']:
            # If a datablock is passed, either as b--0001-0000-0000-0123 or d--0001-0000-0000-0123
            # return the original device: d--0000-0000-0123
            slug = formatted_gdid(slug_elements[1])

        dev = get_object_or_404(Device, slug=slug)

        if dev.has_access(self.request.user):
            return dev

        raise PermissionDenied

    def perform_create(self, serializer):
        if self.request.user.is_staff:
            device = serializer.save(created_by=self.request.user)

            if 'project' in serializer.validated_data:
                # If project is defined, assume we want to claim device as well
                project = serializer.validated_data['project']
                org = project.org
                if org and not org.has_permission(self.request.user, 'can_claim_devices'):
                    raise PermissionDenied('No claim permissions')

                device_claim(device, project, claimed_by=self.request.user)
            else:
                serializer.save(created_by=self.request.user)
        else:
            raise PermissionDenied('Method not allowed by user')

    def perform_update(self, serializer):
        """
        Update Device with GPS info
        """
        if not self.request.user.is_staff:
            obj = self.get_object()
            org = obj.org
            if org and not org.has_permission(self.request.user, 'can_modify_device'):
                raise PermissionDenied('User is not allowed to modify device')

        extras = {}
        if 'state' in serializer.validated_data and 'active' not in serializer.validated_data:
            extras['active'] = serializer.validated_data['state'] != 'N0'

        if 'project' in serializer.validated_data:
            project = serializer.validated_data['project']
            if project:
                extras['org'] = project.org
            else:
                extras['org'] = None

        serializer.save(**extras)

    @swagger_auto_schema(
        method='post',
        request_body=DeviceIsClaimableSerializer,
        responses={
            202: 'Request was accepted',
        }
    )
    @action(methods=['post'], detail=False)
    def claimable(self, request):
        """
        Get the number of Devices that are unclaimed by a Project.
        """
        serializer = DeviceIsClaimableSerializer(data=request.data)
        if serializer.is_valid():

            slugs = serializer.validated_data['slugs']
            results = []
            for slug in slugs:
                try:
                    device = Device.objects.get(slug=slug)
                except Device.DoesNotExist:
                    device = None
                if device:
                    item = {'slug': slug}
                    item['claimable'] = (device.project == None)
                    results.append(item)

            return Response({'count': len(results), 'results': results}, status=status.HTTP_202_ACCEPTED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        method='post',
        request_body=DeviceClaimSerializer,
        responses={
            202: 'Request was accepted',
        }
    )
    @action(methods=['post'], detail=False)
    def claim(self, request):
        """
        Claim a Device for a particular Project.
        Once a Device is claimed and associated with a Project, Stream Data for
        the Device may be recorded and viewed within the Project.
        """
        serializer = DeviceClaimSerializer(data=request.data)
        if serializer.is_valid():
            device_slug = serializer.validated_data['device']
            device = get_object_or_404(Device, slug=device_slug)
            if device.project:
                return Response({'detail': 'Device is not claimable'}, status=status.HTTP_400_BAD_REQUEST)

            # Allow either a project.id or project.slug
            # If slug, we know it has the p--<id> format
            parts = serializer.validated_data['project'].split('--')
            if len(parts) == 2 and (parts[0] == 'p' or parts[0] == 'P'):
                project_slug = serializer.validated_data['project']
                project = get_object_or_404(Project, slug=project_slug)
            else:
                project_id = serializer.validated_data['project']
                if validate_uuid(project_id):
                    project = get_object_or_404(Project, pk=project_id)
                else:
                    return Response({'detail': 'Project is not a Valid Slug or UUID'},
                                    status=status.HTTP_400_BAD_REQUEST)

            if not self.request.user.is_staff:
                org = project.org
                if not org.has_permission(request.user, 'can_claim_devices'):
                    return Response({'detail': 'No claim permissions'}, status=status.HTTP_403_FORBIDDEN)

            device_claim(device, project, claimed_by=self.request.user)

            return Response(
                {'claimed': True, 'device': device_slug, 'project': project.slug, 'project_id': str(project.id)},
                status=status.HTTP_202_ACCEPTED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        method='post',
        request_body=DeviceUnclaimSerializer,
        responses={
            202: 'Request was accepted',
        }
    )
    @action(methods=['post'], detail=True)
    def unclaim(self, request, slug=None):
        """
        Unclaim a Device from a Project.
        When a Device is unclaimed, the previous Stream Data for the Device will be cleaned
        and no longer available.
        """
        serializer = DeviceUnclaimSerializer(data=request.data)
        if serializer.is_valid():
            obj = self.get_object()

            if obj.busy:
                raise PermissionDenied('Device is busy. Operation cannot be completed at this time')

            if not self.request.user.is_staff:
                project = obj.project
                org = project.org
                if org and not org.has_permission(request.user, 'can_claim_devices'):
                    return Response({'detail': 'No unclaim permissions'}, status=status.HTTP_403_FORBIDDEN)

            label = serializer.validated_data['label']
            clean_streams = serializer.validated_data['clean_streams']
            payload = {
                'device': obj.slug,
                'clean_streams': clean_streams,
                'label': label
            }
            DeviceUnClaimAction.schedule(payload)

            msg = f'Unclaimed task was scheduled for {obj.slug}'
            return Response({'unclaimed': obj.slug, 'msg': msg}, status=status.HTTP_202_ACCEPTED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        method='post',
        request_body=DeviceUpgradeSerializer,
        responses={
            202: 'Request was accepted',
        }
    )
    @action(methods=['post'], detail=True)
    def upgrade(self, request, slug=None):
        """
        Notify cloud that a device has been upgraded
        WARNING: This API will be removed soon
        """
        serializer = DeviceUpgradeSerializer(data=request.data)
        if serializer.is_valid():
            obj = self.get_object()
            firmware = serializer.validated_data['firmware']
            msg = 'Device {0} firmware upgraded to {1}'.format(slug, firmware)

            send_device_action_notification(obj, msg, self.request.user)

            return Response({'slug': slug, 'msg': msg}, status=status.HTTP_202_ACCEPTED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        method='get',
        responses={
            200: DeviceExtraInfoSerializer(many=False),
        }
    )
    @action(methods=['get'], detail=True)
    def extra(self, request, slug=None):
        """
        Get general information about this device, including
        the data counts per stream
        """
        obj = self.get_object()
        serializer = DeviceExtraInfoSerializer(obj)
        return Response(serializer.data)

    @swagger_auto_schema(
        method='get',
        responses={
            200: SensorGraphSerializer(many=False),
        }
    )
    @action(methods=['get'], detail=True)
    def sg(self, request, slug=None):
        """
        Get the SensorGraph information for a Device.
        SensorGraph information represents the relationship between a Device and
        the Variables that the Device tracks.
        """
        obj = self.get_object()
        sg = obj.sg
        serializer = SensorGraphSerializer(sg)
        return Response(serializer.data)

    @swagger_auto_schema(
        method='get',
        responses={
            200: DeviceTemplateSerializer(many=False),
        }
    )
    @action(methods=['get'], detail=True)
    def template(self, request, slug=None):
        """
        Get the Device template.
        The Device template represents the specifications of the generic model
        of the IOTile Device.
        """
        obj = self.get_object()
        device_template = obj.template
        serializer = DeviceTemplateSerializer(device_template)
        return Response(serializer.data)

    @swagger_auto_schema(
        method='get',
        responses={
            200: DeviceVersionAttributeReadOnlySerializer(many=True),
        }
    )
    @action(methods=['get'], detail=True)
    def versions(self, request, slug=None):
        """
        Get the current versions for the device
        """
        obj = self.get_object()
        version = DeviceVersionAttribute.objects.current_device_version_qs(device=obj)
        serializer = DeviceVersionAttributeReadOnlySerializer(version, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        method='get',
        responses={
            200: StreamerSerializer(many=True),
        }
    )
    @action(methods=['get'], detail=True)
    def streamers(self, request, slug=None):
        """
        Get the Device Streamers
        """
        obj = self.get_object()
        streamer_qs = obj.streamers.all()
        serializer = StreamerSerializer(streamer_qs, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        method='get',
        operation_description='Get Device Helath Settings',
        responses={
            200: DeviceStatusReadOnlySerializer(many=False),
        }
    )
    @swagger_auto_schema(
        method='patch',
        request_body=DeviceStatusWriteOnlySerializer,
        operation_description='Modify Device Health Settings',
        responses={
            201: DeviceStatusWriteOnlySerializer(many=False),
        }
    )
    @action(methods=['get', 'patch'], detail=True)
    def health(self, request, slug=None):
        """
        Device Health Settings
        """

        obj = self.get_object()
        device_status = DeviceStatus.get_or_create(obj)
        if request.method == 'GET':
            serializer = DeviceStatusReadOnlySerializer(device_status)
            return Response(serializer.data)
        elif request.method == 'PATCH':
            serializer = DeviceStatusWriteOnlySerializer(device_status, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        method='get',
        responses={
            200: DeviceStatusReadOnlySerializer(many=False),
        }
    )
    @action(methods=['get'], detail=True)
    def status(self, request, slug=None):
        """
        Get the status of a Device, which includes the last time data has been uploaded
        """
        obj = self.get_object()
        device_status = DeviceStatus.get_or_create(obj)
        serializer = DeviceStatusReadOnlySerializer(device_status)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        if request.user.is_staff and (request.GET.get('staff', '0') == '1'):
            return super(APIDeviceViewSet, self).create(request)
        return Response({'error': 'Restricted Access. Contact Arch'}, status=status.HTTP_403_FORBIDDEN)

    def update(self, request, *args, **kwargs):
        """        
        Staff Only.
        Updates a single Device item
        """
        return super(APIDeviceViewSet, self).update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Staff Only.
        Delete a Device. Not all users have delete permissions.
        """
        if request.user.is_staff and (request.GET.get('staff', '0') == '1'):
            return super(APIDeviceViewSet, self).destroy(request, *args)
        return Response({'error': 'Restricted Access. Contact Arch'}, status=status.HTTP_403_FORBIDDEN)

    @swagger_auto_schema(
        method='get',
        responses={
            200: DeviceFilterLogSerializer(many=True),
        }
    )
    @action(methods=['get'], detail=True)
    def filterlog(self, request, slug=None):
        """
        Get Filter logs of the device
        """
        obj = self.get_object()
        serializer = DeviceFilterLogSerializer(obj)
        return Response(serializer.data)

    @swagger_auto_schema(
        method='post',
        request_body=DeviceResetSerializer,
        responses={
            202: 'Indicates reset task has been scheduled',
            404: 'Device slug not found'
        }
    )
    @action(methods=['post'], detail=True)
    def reset(self, serializer, slug=None):
        """
        Schedule a backend job to reset the device (Delete all data)
        """
        device = self.get_object()
        org = device.org
        if org and org.has_permission(self.request.user, 'can_reset_device'):

            serializer = DeviceResetSerializer(data=self.request.data)
            if serializer.is_valid():
                if device.busy:
                    raise PermissionDenied('Device is busy. Operation cannot be completed at this time')

                full_reset = serializer.validated_data['full']
                include_properties = serializer.validated_data['include_properties']
                include_notes_and_locations = serializer.validated_data['include_notes_and_locations']
                pid = schedule_reset(
                    device, self.request.user,
                    full_reset=full_reset,
                    include_properties=include_properties,
                    include_notes_and_locations=include_notes_and_locations
                )
                return Response({'reset': 'scheduled', 'pid': str(pid)}, status=status.HTTP_202_ACCEPTED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        else:
            raise PermissionDenied

    @swagger_auto_schema(
        method='post',
        request_body=DeviceDataTrimSerializer,
        responses={
            202: 'Indicates trimming task has been scheduled',
            404: 'Device slug not found'
        }
    )
    @action(methods=['post'], detail=True)
    def trim(self, serializer, slug=None):
        """
        Schedule a backend job to reset the device (Delete all data)

        Datetime format in UTC. Example: `2018-01-01T01:00:00Z`

        """
        device = self.get_object()
        org = device.org
        if org and org.has_permission(self.request.user, 'can_modify_device'):
            serializer = DeviceDataTrimSerializer(data=self.request.data)
            if serializer.is_valid():

                if device.busy:
                    raise PermissionDenied('Device is busy. Operation cannot be completed at this time')

                args = {
                    'device_slug': device.slug,
                    'username': self.request.user.username,
                }
                # Add the start/end arguments from the payload
                args.update(serializer.validated_data)

                DeviceDataTrimAction.schedule(args=args)
                return Response({'trim': 'scheduled'}, status=status.HTTP_202_ACCEPTED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            raise PermissionDenied

    @swagger_auto_schema(
        method='get',
        operation_description='Get current device data mask time ranges',
        responses={
            200: DeviceDataMaskSerializer(many=False),
            404: 'Device slug not found'
        }
    )
    @swagger_auto_schema(
        method='patch',
        request_body=DeviceDataMaskSerializer,
        operation_description='Set time range for device data mask. All data outside range will be masked away (hidden). Datetime format in UTC. Example: `2018-01-01T01:00:00Z`',
        responses={
            202: DeviceDataMaskSerializer(many=False),
            404: 'Device slug not found'
        }
    )
    @swagger_auto_schema(
        method='delete',
        responses={
            204: '',
        }
    )
    @action(methods=['get', 'patch', 'delete'], detail=True)
    def mask(self, request, slug=None):
        """
        Device Data Mask API
        """
        device = self.get_object()
        return mask_api_helper(request=request, obj=device)

    @swagger_auto_schema(
        method='get',
        responses={
            200: 'Key',
        }
    )
    @action(methods=['get'], detail=True)
    def key(self, request, slug=None):
        """
        Get downloadable secret keys
        """
        key_type = self.request.GET.get('type', '')
        if key_type != '':
            key_type = key_type.upper()
            obj = self.get_object()
            if obj.active and key_type.lower() == DEVICE_TOKEN_AUTH_HEADER_PREFIX:
                # 'a-jwt' is special as the key is generated without the need for
                # a record. Instead, tt uses a JWT to encode {device, user and project}
                # on a JWT token that we can use to give access to a given API
                # As user, we are using the user that claimed the device
                if obj.claimed_by is not None:
                    jwt = encode_device_ajwt_key(device=obj, user=obj.claimed_by)
                    return Response({'key': jwt}, status=status.HTTP_200_OK)
            try:
                key = DeviceKey.objects.get_for_download(slug=obj.slug, type=key_type)
            except DeviceKey.DoesNotExist:
                return Response({'msg': 'No key available'}, status=status.HTTP_403_FORBIDDEN)
            return Response({'key': key.secret}, status=status.HTTP_200_OK)
        return Response({'msg': 'No type specified'}, status=status.HTTP_400_BAD_REQUEST)


class ManufacturingDataApiFilter(django_filters.rest_framework.FilterSet):
    dt = django_filters.CharFilter(method='filter_by_dt', label='Device Template')
    sg = django_filters.CharFilter(method='filter_by_sg', label='Sensor Graph')
    claimed = django_filters.BooleanFilter(method='filter_by_claimed', label='Claimed')

    class Meta:
        model = Device
        fields = ['dt', 'sg', 'claimed', 'org__slug']

    def filter_by_dt(self, queryset, name, value):
        dt = get_object_or_404(DeviceTemplate, slug=value)
        return queryset.filter(template=dt)

    def filter_by_sg(self, queryset, name, value):
        sg = get_object_or_404(SensorGraph, slug=value)
        return queryset.filter(sg=sg)

    def filter_by_claimed(self, queryset, name, value):
        return queryset.exclude(project__isnull=True)


class APIManufacturingDataViewSet(viewsets.ModelViewSet):
    """
    API to get IOTile Device Information, Machine-to-machine
    This API is specifically meant to other cloud servers to call IOTile Cloud, who will have
     the master list of device information.
    """
    lookup_field = 'slug'
    queryset = Device.objects.none()
    pagination_class = LargeResultsSetPagination
    permission_classes = (HasAuthAPIKey & ReadOnly, )
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = ManufacturingDataApiFilter
    serializer_class = ManufacturingDataSerializer

    def get_serializer_class(self):
        if self.request.query_params.get("keys", "0") == "1":
            return ManufacturingDataKeysSerializer
        return self.serializer_class

    def get_queryset(self):
        """
        This view should return a list of all devices belonging to
        the specified org and all unclaimed devices
        """

        qs = Device.objects.none()
        apikeyOrg = get_org_slug_from_apikey(self.request)
        if apikeyOrg:
            logger.info("Received device/production/data call with M2M token from org %s" % apikeyOrg)
            qs = Device.objects.filter(org__slug=apikeyOrg)
            return qs.select_related('org', 'template', 'sg')

        return qs

    def get_object(self):
        """
        Get object based on given slug. prepend '0000' as needed to
        properly format the device gid='d--0000-0000-0000-0001'
        Returns: Device if it exist
        """
        slug = self.kwargs.get('slug', None)
        apikeyOrg = get_org_slug_from_apikey(self.request)

        if slug:
            slug_elements = slug.split('--')
            if len(slug_elements) == 2 and slug_elements[0] == 'd':
                slug = formatted_gdid(slug_elements[1])

            dev = get_object_or_404(Device, slug=slug)

            if dev and dev.org and dev.org.slug == apikeyOrg:
                return dev
        raise PermissionDenied

    @action(
        detail=False, methods=['post'],
        permission_classes=[HasAuthAPIKey]
    )
    def create_virtual(self, request):
        """
        Request:
            {
                "qty": int, optional, default 1,
                "sg": str slug,
                "user": str slug, requires active and staff user,
            }
        Response:
            [DeviceSerializer] * qty
        """
        MAX_QTY = 1 # TODO: Could be more
        org_slug = get_org_slug_from_apikey(request)
        try:
            qty = int(request.data.get("qty", 1))
            assert 1 <= qty <= MAX_QTY
        except ValueError:
            return Response(
                {"error": "If provided, qty must be an integer."},
                status.HTTP_400_BAD_REQUEST
            )
        except AssertionError:
            return Response(
                {"error": f"Integer must be between 1 and {MAX_QTY}."},
                status.HTTP_400_BAD_REQUEST
            )
        data = request.data.copy()
        data.update({"org": org_slug})
        serializer = ManufacturingDataVirtualDeviceSerializer(data=[data for i in range(qty)], many=True)
        serializer.is_valid(raise_exception=True)
        devices = serializer.save()
        serializer = DeviceSerializer(devices, many=True)
        return Response(serializer.data, status.HTTP_201_CREATED)
