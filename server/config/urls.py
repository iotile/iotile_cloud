"""server URL Configuration

"""
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import include, path, re_path

from rest_framework import routers
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated

from apps.main.api_views import APIDbStatsViewSet, APIServerInfoViewSet
from apps.ota.api_views import *
from apps.report.api_views import APIReportSummaryGenerationViewSet
from apps.report.views import GeneratedUserReportPublicRedirect
from apps.s3file.api_views import APIFineUploaderSignViewSet
from apps.sqsworker.api_views import APIActionPidViewSet
from apps.streamdata.api_views import APIStreamDataFrameViewSet

from .v1_urls import v1_api_router

# Disable new Django 3.1 admin navigation
admin.site.enable_nav_sidebar = False

urlpatterns = [

    path('', include('apps.main.urls')),
    path('account/', include('apps.authentication.urls')),
    path('staff/', include('apps.staff.urls', namespace='staff')),
    path('org/', include('apps.org.urls', namespace='org')),
    path('vendor/', include('apps.vendor.urls', namespace='vendor')),
    path('dt/', include('apps.devicetemplate.urls', namespace='template')),
    path('pt/', include('apps.projecttemplate.urls', namespace='project-template')),
    path('ot/', include('apps.orgtemplate.urls', namespace='org-template')),
    path('sg/', include('apps.sensorgraph.urls', namespace='sensor-graph')),
    path('component/', include('apps.component.urls', namespace='component')),
    path('variable/', include('apps.stream.urls-var', namespace='variable')),
    path('property/', include('apps.property.urls', namespace='property')),
    path('config/', include('apps.configattribute.urls', namespace='config-attribute')),
    path('location/', include('apps.devicelocation.urls', namespace='devicelocation')),
    path('note/', include('apps.streamnote.urls', namespace='streamnote')),
    path('filter/', include('apps.streamfilter.urls', namespace='filter')),
    path('ota/', include('apps.ota.urls', namespace='ota')),

    path('image/', include('apps.s3images.urls', namespace='s3image')),
    path('file/', include('apps.s3file.urls', namespace='s3file')),
    re_path(r'^share/report/(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/',
            GeneratedUserReportPublicRedirect.as_view(), name='public-report'),

    # Vertical Specific Apps
    path('apps/shipping/', include('apps.verticals.shipping.urls', namespace='apps-shipping')),

    path('admin/', admin.site.urls),

    # Rest API
    path('api/v1/auth/', include('apps.authentication.api_urls')),
    path('api/v1/server/', APIServerInfoViewSet.as_view(), name='api-server'),
    path('api/v1/dbstats/', APIDbStatsViewSet.as_view(), name='api-db-stats'),
    path('api/v1/df/', APIStreamDataFrameViewSet.as_view(), name='api-pd'),
    path('api/v1/report/summary/', APIReportSummaryGenerationViewSet.as_view(), name='api-report-summary'),
    re_path(r'^api/v1/ota/device/(?P<slug>[dD]--0000-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/',
            APIDeploymentDeviceInfoViewSet.as_view(), name='api-ota-device'),

    # Vertical Specifc URLs
    # - Shipping
    path('api/v1/shipping/', include('apps.verticals.shipping.api_urls')),

    # S3File APIs
    path('api/v1/s3file/sign/', APIFineUploaderSignViewSet.as_view(), name='api-s3file-sign'),
    path('api/v1/pid/', APIActionPidViewSet.as_view(), name='api-pid'),

    path('api/v1/', include(v1_api_router.urls)),

    # Healthchecks
    path('health/', include('health_check.urls')),
]

if settings.GENERATE_API_DOCS:
    from drf_yasg import openapi
    from drf_yasg.views import get_schema_view

    from apps.utils.swagger.public_urls import docs_urlpatterns

    swagger_info = openapi.Info(
        title="IOTile Cloud API Documentation",
        default_version='v1',
        description="API to manage devices, setup projects, view data, etc.",
        terms_of_service="/sw-terms/",
        contact=openapi.Contact(email="help@archsys.io"),
    )

    public_schema_view = get_schema_view(
        info=swagger_info,
        public=True,
        patterns=docs_urlpatterns,
        permission_classes=(AllowAny,),
    )

    urlpatterns += [
        re_path(r'^api/swagger(?P<format>.json|.yaml)$', public_schema_view.without_ui(cache_timeout=300), name='schema-json'),
        path('api/docs/', public_schema_view.with_ui('redoc', cache_timeout=300), name='schema-redoc'),
        path('api/swagger/', public_schema_view.with_ui('swagger', cache_timeout=300), name='schema-swagger-ui'),
    ]

    private_schema_view = get_schema_view(
        info=swagger_info,
        public=False,
        permission_classes=(IsStaffOrReadOnly,),
    )

    urlpatterns += [
        path('api/private-docs/', login_required(private_schema_view.with_ui('swagger', cache_timeout=0)), name='private-schema-swagger'),
    ]

if settings.DEBUG and 'debug_toolbar' in settings.INSTALLED_APPS:
    import debug_toolbar
    urlpatterns.append(
        path('__debug__/', include(debug_toolbar.urls)),
    )
