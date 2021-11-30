from rest_framework_jwt.views import obtain_jwt_token, refresh_jwt_token, verify_jwt_token

from django.conf.urls import *

from .api_views import *

urlpatterns = [
    url(r'^login/$', APILoginViewSet.as_view(), name='api-login'),
    url(r'^password/reset/$', PasswordResetView.as_view(), name='reset-password'),
    url(r'^logout/$', APILogoutViewSet.as_view(), name='api-logout'),
    url(r'^token/$', APITokenViewSet.as_view(), name='api-token'),
    url(r'^user-info/$', APIUserInfoViewSet.as_view(), name='api-user-info'),
    url(r'^api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    # url(r'^api-token-auth/', csrf_exempt(obtain_auth_token), name='api-token-auth'),
    url(r'^api-jwt-auth/', obtain_jwt_token, name='api-jwt-auth'),
    url(r'^api-jwt-verify/', verify_jwt_token, name='api-jwt-verify'),
    url(r'^api-jwt-refresh/', refresh_jwt_token, name='api-jwt-refresh'),

]
