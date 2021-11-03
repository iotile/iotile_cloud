import logging

from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import csrf_exempt
from django.utils.translation import gettext_lazy as _

from allauth.account.utils import send_email_confirmation

from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework import permissions, viewsets
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from drf_yasg.utils import no_body, swagger_auto_schema

from apps.utils.rest.permissions import *
from .permissions import IsAccountOwner
from .serializers import *
from .tasks import send_new_user_notification

# Get an instance of a logger
logger = logging.getLogger(__name__)


class APITokenViewSet(APIView):
    """
    View to get User's token
    """
    permission_classes = (permissions.IsAuthenticated,)

    @swagger_auto_schema(
        operation_id='auth-token',
        responses={
            200: '{ "jwt": "JWT Token" }',
        }
    )
    def get(self, request, format=None):
        """
        Get current JWT Token
        """
        data_dic = {}

        token = request.user.drf_token
        data_dic['token'] = token.key

        # For now, also return JWT token as a seperate field
        data_dic['jwt'] = request.user.jwt_token

        return Response(data_dic, status=status.HTTP_200_OK)


class AccountViewSet(viewsets.ModelViewSet):
    """
    User Account information.
    Users belong to an Org, and have access to Project information within that Org
    """
    lookup_field = 'slug'
    queryset = Account.objects.none()
    serializer_class = AccountSerializer

    def get_permissions(self):

        if self.request.method in permissions.SAFE_METHODS:
            return (permissions.IsAuthenticated(),)

        if self.request.method == 'POST':
            return (permissions.AllowAny(),)

        return (permissions.IsAuthenticated(), IsAccountOwner(),)

    def get_queryset(self):
        """
        This view should return a list of all records
        """
        if self.request.user.is_staff and self.request.GET.get('staff', ''):
            return Account.objects.all()

        return Account.objects.filter(pk=self.request.user.id)

    @csrf_exempt
    def create(self, request, *args, **kwargs):
        '''
        Create a new Account. Requires a Recatcha Token
        '''

        serializer = self.serializer_class(data=request.data)

        if serializer.is_valid() and 'password' in serializer.validated_data and 'confirm_password' in serializer.validated_data:
            '''
            When you create an object using the serializer's .save() method, the
            object's attributes are set literally. This means that a user registering with
            the password 'password' will have their password stored as 'password'. This is bad
            for a couple of reasons: 1) Storing passwords in plain text is a massive security
            issue. 2) Django hashes and salts passwords before comparing them, so the user
            wouldn't be able to log in using 'password' as their password.

            We solve this problem by overriding the .create() method for this viewset and
            using Account.objects.create_user() to create the Account object.
            '''
            password = serializer.validated_data['password']
            confirm_password = serializer.validated_data['confirm_password']
            verified_email = serializer.validated_data.get('verified_email', False)
            if 'captcha_token' in serializer.validated_data:
                captcha_token = serializer.validated_data.get('captcha_token')
                logger.warning('Captcha Token ignored: {}'.format(captcha_token))

            if password and confirm_password and password == confirm_password:

                # Note that for now, Accounts default to is_active=False
                # which means that we need to manually active them
                # This is to keep the site secure until we go live
                account = Account.objects.create_user(**serializer.validated_data)

                account.set_password(serializer.validated_data['password'])
                if not (verified_email and request.user.is_staff):
                    account.is_active = False
                account.save()

                # Send django-allauth verification email
                if verified_email and request.user.is_staff:
                    # If user created by staff and this flag is set, set Email as Verified
                    EmailAddress.objects.create(email=account.email, user=account, verified=True, primary=True)
                else:
                    EmailAddress.objects.create(email=account.email, user=account, verified=False, primary=True)
                    send_email_confirmation(request._request, account)

                # For now, we also want to email Admin every time anybody registers
                send_new_user_notification(id=account.id, username=account.username, email=account.email)

                ret_data = {
                    'id': account.id,
                    'slug': account.slug,
                    'created_at': account.created_at,
                }
                for item in ['username', 'email', 'name', 'tagline']:
                    if item in serializer.validated_data:
                        ret_data[item] = serializer.validated_data[item]

                return Response(ret_data, status=status.HTTP_201_CREATED)
            else:
                raise ValidationError('Passwords did not match')

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['post'], detail=True)
    def set_password(self, request, slug=None):
        """
        Reset the password for a single Account
        """
        account = self.get_object()
        serializer = PasswordCustomSerializer(data=request.data)
        if serializer.is_valid():
            account.set_password(serializer.data['password'])
            account.save()

            return Response({'status': 'password set'}, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, *args, **kwargs):
        """Returns a single Account item given that Account's username 
        Username should be in the form of a slug """
        slug = kwargs['slug']
        return super(AccountViewSet, self).retrieve(request, slug)

    def update(self, request, *args, **kwargs):
        """Updates a single Account item"""
        return super(AccountViewSet, self).update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Partially update an Account """
        return super(AccountViewSet, self).partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Staff Only.
        Delete an Account
        """
        slug = kwargs['slug']
        return super(AccountViewSet, self).destroy(request, slug)


class APILoginViewSet(APIView):
    """
    Custom Login function.
    Returns user info and tokens if successful
    """

    @swagger_auto_schema(
        operation_id='auth-login',
        request_body=LoginCustomSerializer,
        responses={
            201: AccountSerializer(),
        }
    )
    @csrf_exempt
    def post(self, request, format=None):
        """
        Secondary login method. Uses email and password
        Recommendation: Use `POST:/api/v1/auth/api-jwt-auth/` instead
        """
        data = JSONParser().parse(request)
        serializer = LoginCustomSerializer(data=data)

        if serializer.is_valid():
            email = serializer.data.get('email')
            password = serializer.data.get('password')

            if not request.user.is_anonymous:
                return Response('Already Logged-in', status=status.HTTP_403_FORBIDDEN)

            account = authenticate(email=email, password=password)

            if account is not None:
                if account.is_active:
                    login(request, account)

                    serialized = AccountSerializer(account)
                    data = serialized.data

                    # Add the token to the return serialization
                    token = request.user.drf_token
                    data['token'] = token.key

                    # For now, also return JWT token as a seperate field
                    data['jwt'] = request.user.jwt_token

                    return Response(data)
                else:
                    return Response('This account is not Active.', status=status.HTTP_401_UNAUTHORIZED)
            else:
                return Response('Username/password combination invalid.', status=status.HTTP_401_UNAUTHORIZED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    """
    def get(self, request, format=None):
        data_dic = {"Error":"GET not supported for this command"}
        logout(request)
        mystatus = status.HTTP_400_BAD_REQUEST
        return Response(data_dic, status=mystatus)
    """


class APILogoutViewSet(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @swagger_auto_schema(
        operation_id='auth-logout',
        responses={
            204: 'Empty',
        }
    )
    def post(self, request, format=None):
        """Logout from session"""
        logout(request)

        return Response({}, status=status.HTTP_204_NO_CONTENT)


class APIUserInfoViewSet(APIView):
    """
    View to list all users in the system.

    * Requires token authentication.
    * Only admin users are able to access this view.
    """
    #permission_classes = ()

    @swagger_auto_schema(
        operation_id='auth-user-info',
        responses={
            200: AccountSerializer(),
        }
    )
    @csrf_exempt
    def get(self, request, format=None):
        """
        Get User Account Information
        Name, Email, Avatar, etc.
        """
        if request.user.is_anonymous:
            # User most login before they can get a token
            # This not only ensures the user has registered, and has an account
            # but that the account is active
            return Response('User not recognized.', status=status.HTTP_403_FORBIDDEN)

        account = request.user

        serialized = AccountSerializer(account)
        data = serialized.data

        # For now, also return JWT token as a seperate field
        data['jwt'] = request.user.jwt_token

        return Response(data)


class PasswordResetView(GenericAPIView):
    """
    Calls Django Auth PasswordResetForm save method.
    Accepts the following POST parameters: email
    Returns the success/fail message.
    """
    serializer_class = PasswordResetSerializer
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        # Create a serializer with request.data
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if Account.objects.filter(email=serializer.validated_data['email']).count() == 0:
            return Response(
                {"detail": _("No account associated to that email address")},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer.save()
        # Return the success message with OK HTTP status
        return Response(
            {"detail": _("Password reset e-mail has been sent.")},
            status=status.HTTP_200_OK
        )
