from django.contrib.auth import get_user_model

from rest_framework import serializers

from .models import Invitation

user_model = get_user_model()


class SendInvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = ('email',)
        read_only_fields = ('id', 'created_on',)


class PendingInvitationsSerializer(serializers.ModelSerializer):
    sent_by = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=user_model.objects.all()
    )
    class Meta:
        model = Invitation
        fields = ('email', 'sent_on', 'sent_by', )
        read_only_fields = ('email', 'sent_on', 'sent_by', )



