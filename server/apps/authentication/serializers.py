from django.contrib.auth import update_session_auth_hash
from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm
from allauth.account.utils import user_pk_to_url_str
from allauth.account.forms import EmailAwarePasswordResetTokenGenerator

from rest_framework import serializers

from allauth.account.models import EmailAddress

from .models import Account


default_token_generator = EmailAwarePasswordResetTokenGenerator()


class AccountSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    confirm_password = serializers.CharField(write_only=True, required=False)
    verified_email = serializers.BooleanField(write_only=True, required=False)
    captcha_token  = serializers.CharField(required=False)
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = ('id', 'email', 'username', 'created_at', 'updated_at',
                  'name', 'tagline', 'avatar', 'password',
                  'confirm_password', 'verified_email', 'slug', 'is_staff', 'captcha_token')
        read_only_fields = ('created_at', 'updated_at', 'avatar', 'slug', 'is_staff',)
        extra_kwargs = {
            'password': {'write_only': True},
            'confirm_password': {'write_only': True},
            'verified_email': {'write_only': True},
        }

    def to_representation(self, obj):
        data = super(AccountSerializer, self).to_representation(obj)
        return data

    def get_avatar(self, obj):
        return {
            'tiny': obj.get_gravatar_tiny_url(),
            'thumbnail': obj.get_gravatar_thumbnail_url(),
            'medium': obj.get_gravatar_medium_url(),
        }

    def validate_username(self, username):
        # Check that the username does not have a space in it
        if ' ' in username:
            raise serializers.ValidationError("Username cannot have spaces")
        return username


class AccountReadOnlyLightSerializer(serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = ('email', 'username', 'slug', 'name', 'tagline', 'avatar',)
        read_only_fields = ('email', 'username', 'slug', 'name', 'tagline', 'avatar',)

    def get_avatar(self, obj):
        return {
            'tiny': obj.get_gravatar_tiny_url(),
            'thumbnail': obj.get_gravatar_thumbnail_url(),
        }


class LoginCustomSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=200)
    password = serializers.CharField(max_length=200)


class PasswordCustomSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=200)


class PasswordResetSerializer(serializers.Serializer):
    """
    Serializer for requesting a password reset e-mail.
    """
    email = serializers.EmailField()

    password_reset_form_class = PasswordResetForm

    domain = getattr(settings, 'DOMAIN_BASE_URL')

    def validate_email(self, value):
        # Create PasswordResetForm with the serializer
        self.reset_form = self.password_reset_form_class(data=self.initial_data)
        if not self.reset_form.is_valid():
            raise serializers.ValidationError(self.reset_form.errors)

        return value

    def save(self):
        request = self.context.get('request')
        # Set some values to trigger the send_email method.
        opts = {
            'from_email': getattr(settings, 'DEFAULT_FROM_EMAIL'),
            'request': request
        }

        user = Account.objects.get(email=self.reset_form.cleaned_data['email'])

        self.reset_form.save(
            domain_override=getattr(settings, 'DOMAIN_BASE_URL'),
            html_email_template_name='registration/password_reset_email_html.html',
            extra_email_context={
                'uidb36': user_pk_to_url_str(user),
                'key': default_token_generator.make_token(user),
                'site_name': getattr(settings, 'SITE_NAME'),
                'site_domain': getattr(settings, 'DOMAIN_NAME'),
            },
            **opts
        )
