import json
from django.http import HttpResponse, Http404
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

import django_filters
from rest_framework import viewsets
from rest_framework import mixins
from rest_framework import status
from rest_framework import filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import exceptions

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from apps.project.serializers import ProjectSerializer
from apps.utils.rest.pagination import LargeResultsSetPagination
from apps.invitation.serializers import SendInvitationSerializer, PendingInvitationsSerializer
from apps.invitation.models import Invitation
from apps.datablock.documents import DataBlockDocument
from apps.datablock.serializers import DataBlockSerializer
from apps.physicaldevice.documents import DeviceDocument
from apps.physicaldevice.serializers import DeviceSerializer

from .models import *
from .permissions import IsMemberOnly
from .serializers import *
from .tasks import send_new_org_notification


class APIOrgViewSet(viewsets.ModelViewSet):
    """
    An Organization represents a group of users that want to share project and device information.
    
    Organizations are usually use to represent Companies, but in reality, can represent anything.
    
    Users belong to Organizations (as organization members), and have access to all Projects and Device data associated to that Organization.
    
    Organization Admins have additional powers compared to normal members.
    """
    lookup_field = 'slug'
    queryset = Org.objects.none()
    serializer_class = OrgSerializer
    permission_classes = (IsMemberOnly,)
    filterset_fields = ('created_by',)
    filter_backends = (filters.SearchFilter, django_filters.rest_framework.DjangoFilterBackend,)
    search_fields = ('name',)

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        all = self.request.user.is_staff and (self.request.GET.get('staff', '0') == '1')
        if all:
            return Org.objects.all().prefetch_related('created_by')

        return Org.objects.user_orgs_qs(self.request.user).prefetch_related('created_by')

    def perform_create(self, serializer):
        """
        Create a new Org.
        Orgs can't have the same name as an existing Org.
        """
        # Make sure name won't produce duplicate slug
        name = serializer.validated_data['name']
        slug = slugify(name)
        if Org.objects.filter(slug=slug).exists():
            raise exceptions.ValidationError('Organization with this Name produces duplicate slug.')

        instance = serializer.save(created_by=self.request.user)
        instance.register_user(user=self.request.user, is_admin=True, role='a0')

        # For now, we also want to email Admin every time anybody registers
        send_new_org_notification(instance)

    def _search(self, org, document, filters):
        from elasticsearch_dsl import Q

        s = document.search()
        # .highlight('title', 'label', 'properties.*') TO BE ADDED
        s = s.filter("term", org=org.slug)
        query = filters.pop('q', None)
        page_number = int(filters.pop('page', '1')[0])
        start = (page_number-1) * 10
        end = start + 10

        if query:
            query = query[0]
            s = s.query("multi_match", query=query, operator="and", type="cross_fields",
                fields=[
                    'title',
                    'label',
                    'properties_val',
                    'description',
                    'slug',
                    'template',
                    'sensorgraph',
                    'notes',
                    'created_by',
                    'claimed_by',
                ]
            )

        if filters:
            for key, value in filters.items():
                s = s.filter("nested", path="properties",
                    query=Q({
                        "bool" : {
                            "must" : [
                                Q("term", properties__key_term=key),
                                Q("term", properties__value_term=value)
                            ]
                        }
                    })
                )

        # TO BE ADDED
        # response = s.execute()
        # for element, hit in zip(qs, response):
        #     if 'highlight' in hit.meta:
        #         for fragment in hit.meta.highlight:
        #             setattr(element, fragment, hit.meta.highlight[fragment][0])

        if page_number <= 1:
            prev_p = None
        else:
            prev_p = page_number - 1
        
        if page_number * 10 >= s.count():
            next_p = None
        else:
            next_p = page_number + 1

        return s.count(), s[start:end].to_queryset(), next_p, prev_p


    @swagger_auto_schema(
        method='get',
        responses={
            200: DataBlockSerializer(many=True),
        }
    )
    @action(methods=['get'], detail=True)
    def archives(self, request, slug=None):
        """
         Return all Archives owned by this Org
        """
        org = self.get_object()
        if not org:
            return Response([], status=status.HTTP_200_OK)

        filters = request.GET.copy()

        count, page, next_p, prev_p  = self._search(org, DataBlockDocument, filters)

        serializer = DataBlockSerializer(page, many=True)
        return Response({
            'next_page': next_p, 
            'prev_page': prev_p,
            'count': count,
            'results': serializer.data
        })



    @swagger_auto_schema(
        method='get',
        responses={
            200: DeviceSerializer(many=True),
        }
    )
    @action(methods=['get'], detail=True)
    def devices(self, request, slug=None):
        """
         Return all Devices owned by this Org
        """
        org = self.get_object()
        if not org:
            return Response([], status=status.HTTP_200_OK)

        filters = request.GET.copy()
        count, page, next_p, prev_p  = self._search(org, DeviceDocument, filters)

        serializer = DeviceSerializer(page, many=True)
        return Response({
            'next_page': next_p, 
            'prev_page': prev_p,
            'count': count,
            'results': serializer.data
        })


    @swagger_auto_schema(
        method='get',
        responses={
            200: ProjectSerializer(many=True),
        }
    )
    @action(methods=['get'], detail=True)
    def projects(self, request, slug=None):
        """
         Return all Projects owned by this Org
        """
        org = self.get_object()

        qs = org.projects.all().order_by('name')

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = ProjectSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ProjectSerializer(qs, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method='get',
        responses={
            200: OrgMembershipSerializer(many=True),
        },
        manual_parameters=[
            openapi.Parameter(
                name='all', in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                description="Set to 1 to include disabled members. Defaults to 0",
                required=True
            ),
        ]

    )
    @action(methods=['get'], detail=True)
    def members(self, request, slug=None):
        """
         Return all list of Organization members.
        """
        org = self.get_object()

        if  not org.has_permission(request.user, 'can_manage_users'):
            raise exceptions.PermissionDenied('Access Denied due to lack of sufficient permissions')

        all = (self.request.GET.get('all', '0') == '1')
        if all:
            qs = org.membership.all()
        else:
            qs = org.membership.filter(is_active=True)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = OrgMembershipSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = OrgMembershipSerializer(qs, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method='get',
        responses={
            200: PendingInvitationsSerializer(many=True),
        }
    )
    @action(methods=['get'], detail=True)
    def pending(self, request, slug=None):
        """
         Return the list of pending invitations.
         i.e. emails that were sent, and users have not acted on.
        """
        org = self.get_object()
        if not org.has_permission(request.user, 'can_manage_users'):
            raise exceptions.PermissionDenied('Access Denied due to lack of sufficient permissions')

        qs = Invitation.objects.pending_invitations(org=org)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = PendingInvitationsSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = PendingInvitationsSerializer(qs, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method='get',
        responses={
            200: OrgMembershipSerializer(many=False),
        }
    )
    @action(methods=['get'], detail=True)
    def membership(self, request, slug=None):
        """
         Return details on current user Org Membership
        """
        membership = OrgMembership.objects.get(org=self.get_object(), user=self.request.user)

        serializer = OrgMembershipSerializer(membership)

        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method='get',
        responses={
            200: OrgExtraInfoSerializer(many=False)
        }
    )
    @action(methods=['get'], detail=True)
    def extra(self, request, slug=None):
        """
         Return org details, including current user permissions, and relevant record counts
        """
        org = self.get_object()
        serializer = OrgExtraInfoSerializer(org, context={"request": request})

        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method='post',
        request_body=SendInvitationSerializer,
        responses={
            201: SendInvitationSerializer(many=False)
        }
    )
    @action(methods=['post'], detail=True)
    def invite(self, request, slug=None):
        """
         Send (or resend) email invitation to join Org
        """
        org = self.get_object()

        serializer = SendInvitationSerializer(data=request.data)
        if serializer.is_valid():
            if not org.has_permission(request.user, 'can_manage_users'):
                raise exceptions.PermissionDenied('Access Denied due to lack of sufficient permissions')

            email = serializer.validated_data['email']
            try:
                instance = Invitation.objects.get(email=email, org=org)
                if not instance.accepted:
                    instance.sent_by = request.user
                    instance.sent_on = timezone.now()
            except Invitation.DoesNotExist:
                instance = serializer.save(org=org, sent_on=timezone.now(), sent_by=request.user)

            # Send (or resend) invitation
            if not instance.accepted:
                instance.send_email_notification(request=request)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        method='post',
        request_body=OrgMembershipSerializer,
        responses={
            201: OrgMembershipSerializer(many=False)
        }
    )
    @action(methods=['post'], detail=True)
    def register(self, request, slug=None):
        """
         Register an existing User as a member of this Org. Won't send invitation
        """
        org = self.get_object()

        serializer = OrgMembershipSerializer(data=request.data)
        if serializer.is_valid():
            if not org.has_permission(request.user, 'can_manage_users'):
                raise exceptions.PermissionDenied('Access Denied due to lack of sufficient permissions')

            member = serializer.validated_data['user']
            role = serializer.validated_data['role']
            if not OrgMembership.objects.filter(user=member, org=org).exists():
                # Issue#1191: For now, hard code condition to set old is_admin
                serializer.save(org=org, is_org_admin=role in ['a0', 'a1'])
            else:
                return Response({'error': 'Member already exists'}, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def create(self, request, *args, **kwargs):
        """
        Creates an Org object.
        When an Org is created, the creator's user Account is automatically made
        a member of that Org.
        """
        return super(APIOrgViewSet, self).create(request)

    def update(self, request, *args, **kwargs):
        """Updates a single Org item"""
        org = self.get_object()
        if not org.has_permission(request.user, 'can_manage_org_and_projects'):
            raise exceptions.PermissionDenied('Access Denied due to lack of sufficient permissions')

        return super(APIOrgViewSet, self).update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Partially update an Org """
        org = self.get_object()
        if not org.has_permission(request.user, 'can_manage_org_and_projects'):
            raise exceptions.PermissionDenied('Access Denied due to lack of sufficient permissions')

        return super(APIOrgViewSet, self).partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Staff Only.
        Contact Arch Systems to deactivate your Organization
        """
        if request.user.is_staff and (request.GET.get('staff', '0') == '1'):
            return super(APIOrgViewSet, self).destroy(request, args, kwargs)
        return Response({'error': 'Restricted Access. Contact Arch'}, status=status.HTTP_403_FORBIDDEN)
