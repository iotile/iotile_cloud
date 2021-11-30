from django.contrib.auth import get_user_model

from rest_framework import serializers

from apps.authentication.models import Account

from .models import *

user_model = get_user_model()


class FleetSerializer(serializers.ModelSerializer):
    created_by = serializers.SlugRelatedField(
        slug_field='slug',
        read_only=True
    )
    org = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Org.objects.all()
    )
    class Meta:
        model = Fleet
        fields = ('id', 'name', 'slug', 'org', 'description', 'created_on', 'created_by', 'is_network')
        read_only_fields = ('created_on', 'slug')



class FleetMembershipSerializer(serializers.ModelSerializer):
    device = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Device.objects.all()
    )
    class Meta:
        model = FleetMembership
        fields = ('device', 'always_on', 'is_access_point' )

