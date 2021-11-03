from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.authentication.serializers import AccountReadOnlyLightSerializer
from apps.orgtemplate.serializers import OrgTemplateSerializer
from .models import Org, OrgMembership
from .roles import ORG_ROLE_CHOICES

user_model = get_user_model()


class OrgSerializer(serializers.ModelSerializer):
    created_by = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    ot = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    avatar = serializers.SerializerMethodField()
    class Meta:
        model = Org
        fields = ('id', 'name', 'slug', 'ot', 'about', 'created_on', 'created_by', 'avatar', 'domain_names')
        read_only_fields = ('created_on', 'slug', 'domain_names')

    def get_avatar(self, obj):
        return {
            'tiny': obj.get_avatar_tiny_url(),
            'thumbnail': obj.get_avatar_thumbnail_url()
        }


class OrgMembershipSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=user_model.objects.all()
    )
    user_details = serializers.SerializerMethodField(
        help_text='Nested User Object'
    )
    role = serializers.ChoiceField(choices=ORG_ROLE_CHOICES[2:], default='m1')
    role_name = serializers.SerializerMethodField(
        help_text='Named Role'
    )
    class Meta:
        model = OrgMembership
        fields = ('user', 'user_details', 'created_on', 'is_active', 'is_org_admin', 'permissions', 'role', 'role_name')
        read_only_fields = ('created_on', 'info', 'permissions', 'role_name')

    def get_user_details(self, obj):
        serializer = AccountReadOnlyLightSerializer(obj.user)
        return serializer.data

    def get_role_name(self, obj):
        for role in ORG_ROLE_CHOICES:
            if role[0] == obj.role:
                return role[1]
        return 'Unknown Role'


class OrgExtraInfoSerializer(OrgSerializer):
    counts = serializers.SerializerMethodField()
    current_member = serializers.SerializerMethodField()
    ot = OrgTemplateSerializer()
    class Meta:
        model = Org
        fields = ('id', 'name', 'ot', 'slug', 'about', 'created_on', 'created_by', 'avatar', 'counts', 'current_member')
        read_only_fields = ('created_on', 'slug', 'ot')

    def get_counts(self, obj):
        return {
            'projects': obj.projects.count(),
            'datablocks': obj.data_blocks.count(),
            'members': obj.member_count(),
            'devices': obj.devices.count(),
            'fleets': obj.fleets.count(),
            'networks': obj.fleets.filter(is_network=True).count(),
            'reports': obj.reports.count(),
        }

    def get_current_member(self, obj):
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            user = request.user
            try:
                membership = OrgMembership.objects.get(org=obj, user=user)
            except OrgMembership.DoesNotExist:
                return {}
            serializer = OrgMembershipSerializer(membership)
            return serializer.data
        return {}
