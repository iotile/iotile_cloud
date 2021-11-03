import jwt
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.utils.encoding import smart_str

from rest_framework.authentication import get_authorization_header
from rest_framework import exceptions

from rest_framework_jwt.authentication import BaseJSONWebTokenAuthentication

from apps.physicaldevice.models import Device
from .models import DeviceKey

DEVICE_TOKEN_AUTH_HEADER_PREFIX = 'a-jwt'
user_model = get_user_model()


def encode_device_ajwt_key(device, user):
    if device.active and device.project_id:
        payload = {
            'user': user.slug,
            'device': device.slug,
            'project': str(device.project_id)
        }
        # Get secret key from DeviceKey
        key = DeviceKey.objects.get_or_create_ajwt_device_key(device, created_by=user)
        encoded = jwt.encode(payload, key.secret, algorithm='HS256')
        return encoded
    return b''


class DeviceTokenAuthentication(BaseJSONWebTokenAuthentication):

    www_authenticate_realm = 'api'

    def get_ajwt_value(self, request):
        auth = get_authorization_header(request).split()

        if not auth:
            return None

        if smart_str(auth[0].lower()) != DEVICE_TOKEN_AUTH_HEADER_PREFIX:
            return None

        if len(auth) == 1:
            msg = _('Invalid Authorization header. No credentials provided.')
            raise exceptions.AuthenticationFailed(msg)
        elif len(auth) > 2:
            msg = _('Invalid Authorization header. Credentials string '
                    'should not contain spaces.')
            raise exceptions.AuthenticationFailed(msg)

        return auth[1]

    def authenticate(self, request):
        """
        Returns a two-tuple of `User` and token if a valid signature has been
        supplied using JWT-based authentication.  Otherwise returns `None`.
        """
        jwt_value = self.get_ajwt_value(request)

        if jwt_value is None:
            # By retuning None, other authentication schemes will be tried by DRF
            return None

        # 1. Get the unverified payload from JWT
        try:
            unverified_payload = jwt.decode(jwt_value, None, False)
        except jwt.DecodeError:
            msg = _('Error decoding signature.')
            raise exceptions.AuthenticationFailed(msg)
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed()

        # 2. Use unverifed payload to get Device Slug
        if 'device' not in unverified_payload:
            msg = _('No device in payload.')
            raise exceptions.AuthenticationFailed(msg)

        # 3. Use Device Sklug to try to find a DeviceKey for
        try:
            key = DeviceKey.objects.get(slug=unverified_payload['device'], type='A-JWT-KEY')
        except DeviceKey.DoesNotExist:
            msg = _('No secret key found for device')
            raise exceptions.AuthenticationFailed(msg)

        # 4. Get DeviceKey as secret for JWT decoder
        try:
            payload = jwt.decode(jwt_value, key.secret, True, algorithms=['HS256'])
        except jwt.DecodeError:
            msg = _('Error decoding signature.')
            raise exceptions.AuthenticationFailed(msg)
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed()

        # 5. Actual User Authentication (User in payload)
        user = self.authenticate_credentials(payload)

        return user, payload

    def authenticate_credentials(self, payload):

        try:
            device = Device.objects.select_related('claimed_by').get(slug=payload['device'])
        except Device.DoesNotExist:
            raise exceptions.AuthenticationFailed(_('Invalid Device Slug'))

        if not device.active or device.claimed_by is None:
            msg = _('Device is not claimed.')
            raise exceptions.AuthenticationFailed(msg)

        if str(device.project_id) != payload['project']:
            msg = _('Token has incorrect Project')
            raise exceptions.AuthenticationFailed(msg)

        try:
            user = user_model.objects.get(slug=payload['user'])
        except user_model.DoesNotExist:
            raise exceptions.AuthenticationFailed(_('Invalid User Slug'))

        return user
