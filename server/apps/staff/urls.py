from django.conf.urls import *

from .app_specific.factory.views import (
    ArchFXCreateDeviceBatchView, StaffStreamerReportForwarderAddView, StaffStreamerReportForwarderDeleteView,
    StaffStreamerReportForwarderListView, StaffStreamerReportForwarderToggleView,
)
from .app_specific.shipping.views import (
    StaffClaimShippingDeviceView, StaffNewShippingOrgView, StaffNewShippingProjectView,
    StaffShippingDeviceTimestampFixView, StaffShippingView,
)
from .views import *

app_name = 'staff'

urlpatterns = [
    url(r'^$', StaffIndexView.as_view(), name='home'),
    url(r'^ops$', StaffOpsStatusView.as_view(), name='ops-status'),
    url(r'^ses/', include('django_ses.urls')),
    url(r'^worker/', include('apps.sqsworker.urls', namespace='worker')),
    url(r'^cache', StaffOpsCacheView.as_view(), name='ops-cache'),
    url(r'^map/$', StaffMapView.as_view(), name='map'),
    url(r'^user/$', StaffUserListView.as_view(), name='user-list'),
    url(r'^user/new/$', StaffNewUserView.as_view(), name='user-create'),
    url(r'^user/(?P<slug>[-\w]+)/$', StaffUserDetailView.as_view(), name='user-detail'),
    url(r'^org$', StaffOrgListView.as_view(), name='org-list'),
    url(r'^org/(?P<slug>[^/]+)/$', StaffOrgDetailView.as_view(), name='org-detail'),
    url(r'^org/(?P<org_slug>[^/]+)/(?P<slug>[^/]+)/$', StaffProjectDetailView.as_view(), name='project-detail'),
    url(r'^stream/$', StaffStreamsView.as_view(), name='streams'),
    url(
        r'^streamer-report-upload/$', StaffStreamerReportUploadView.as_view(),
        name='streamer-report-upload'
    ),
    url(
        r'^s3/signature/', StaffStreamerReportUploadHandleS3View.as_view(),
        name='streamer-report-upload-signee'
    ),
    url(
        r'^s3/success/$', StaffStreamerReportUploadSuccessEndpointView.as_view(),
        name='streamer-report-upload-success'
    ),
    url(
        r'^stream/(?P<slug>[sS]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}--[a-fA-F0-9]{4})/data/delete/$',
        StaffStreamDataDeleteView.as_view(), name='stream-data-delete'
    ),
    url(
        r'^stream/(?P<slug>[sS]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}--[a-fA-F0-9]{4})/data/delete-confirm/$',
        StaffStreamDataDeleteConfirmView.as_view(), name='stream-data-delete-confirm'
    ),
    url(r'^iotile/batch/$', StaffCreateDeviceBatchView.as_view(), name='iotile-batch'),
    url(r'^upgrade-sg/batch/$', StaffBatchUpgradeSgView.as_view(), name='upgrade-sg-batch'),
    url(
        r'^upgrade-sg/(?P<pk_from>\d+)/(?P<pk_to>\d+)/batch/$',
        StaffBatchUpgradeSgConfirmView.as_view(),
        name='upgrade-sg-batch-confirm'
    ),
    url(
        r'^upgrade-dt/batch/$',
        StaffBatchUpgradeDeviceTemplateView.as_view(),
        name='upgrade-dt-batch'
    ),
    url(
        r'^upgrade-dt/(?P<pk_from>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/(?P<pk_to>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/batch/$',
        StaffBatchUpgradeDeviceTemplateConfirmView.as_view(),
        name='upgrade-dt-batch-confirm'
    ),

    url(r'^project/$', StaffProjectListView.as_view(), name='project-list'),
    url(r'^project/move/$', StaffProjectMoveView.as_view(), name='project-move'),
    url(
        r'^project/(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/move/(?P<org_slug>[^/]+)/$',
        StaffProjectMoveConfirmView.as_view(), name='project-move-confirm'
    ),
    url(r'^project/delete/$', StaffProjectDeleteView.as_view(), name='project-delete'),
    url(
        r'^project/(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/delete/$',
        StaffProjectDeleteConfirmView.as_view(), name='project-delete-confirm'
    ),

    url(r'^device/(?P<pk>\d+)/unclaim/$', StaffDeviceUnclaimConfirmView.as_view(), name='device-unclaim-confirm'),
    url(r'^device/(?P<pk>\d+)/claim/$', StaffDeviceClaimConfirmView.as_view(), name='device-claim-confirm'),
    url(r'^device/(?P<pk>\d+)/semiclaim/$', StaffDeviceSemiClaimConfirmView.as_view(), name='device-semiclaim-confirm'),
    url(r'^device/(?P<pk>\d+)/filter/$', StaffDeviceFilterView.as_view(), name='device-filter-list'),
    url(r'^test/email/$', TestEmailView.as_view(), name='test-email'),
    url(r'^device/(?P<pk>\d+)/detail/$', StaffDeviceDetailView.as_view(), name='device-detail'),
    url(r'^device/(?P<pk>\d+)/keys/$', StaffDeviceKeysDetailView.as_view(), name='keys'),
    url(r'^device/(?P<pk>\d+)/upgrade-config/$', StaffDeviceUpgradeConfigView.as_view(), name='device-upgrade-config'),
    url(
        r'^device/(?P<pk>\d+)/reset-keys/$', StaffDeviceResetKeysConfirmView.as_view(),
        name='device-reset-key-confirm'
    ),
    url(r'^device/data/move/$', StaffDeviceDataMoveView.as_view(), name='device-data-move'),
    url(
        r'^device/(?P<dev0>\d+)/move/(?P<dev1>\d+)/$', StaffDeviceDataMoveConfirmView.as_view(),
        name='device-data-move-confirm'
    ),
    url(r'^gateway/$', StaffGatewayStatusView.as_view(), name='gateway'),
    url(r'^sg/matrix/$', StaffSensorGraphMatrixView.as_view(), name='sg-matrix'),
    url(r'^sms/send/$', StaffSmsSendView.as_view(), name='sms-send'),
    # url(r'^streamtimeseries/data/migrate/$', StaffStreamTimeSeriesMigrateDataView.as_view(), name='streamtimeseries-migrate-data'),
    # url(r'^streamtimeseries/data/(?P<pk>\d+)/$', StaffStreamTimeSeriesValueDetailView.as_view(), name='streamtimeseriesvalue-detail'),
    # url(r'^streamtimeseries/event/migrate/$', StaffStreamTimeSeriesMigrateEventView.as_view(), name='streamtimeseries-migrate-event'),
    # url(r'^streamtimeseries/event/(?P<pk>\d+)/$', StaffStreamTimeSeriesEventDetailView.as_view(), name='streamtimeseriesevent-detail'),

    # App Specifc: Shipping
    url(r'^shipping/$', StaffShippingView.as_view(), name='shipping'),
    url(r'^shipping/org/add/$', StaffNewShippingOrgView.as_view(), name='shipping-org'),
    url(r'^shipping/project/add/$', StaffNewShippingProjectView.as_view(), name='shipping-project'),
    url(
        r'^shipping/device/claim/$',
        StaffClaimShippingDeviceView.as_view(), name='shipping-claim'
    ),
    url(
        r'^shipping/device/data/fix/$',
        StaffShippingDeviceTimestampFixView.as_view(), name='shipping-data-fix'
    ),

    # App Specifc: Factory
    url(r'^factory/device/create/$', ArchFXCreateDeviceBatchView.as_view(), name='factory-batch-device'),
    url(
        r'^factory/forwarder/$',
        StaffStreamerReportForwarderListView.as_view(),
        name='streamer-report-forwarder'
    ),
    url(
        r'^factory/forwarder/add/$',
        StaffStreamerReportForwarderAddView.as_view(),
        name='streamer-report-forwarder-add'
    ),
    url(
        r'^factory/forwarder/(?P<pk>\d+)/delete/$',
        StaffStreamerReportForwarderDeleteView.as_view(),
        name='streamer-report-forwarder-delete'
    ),
    url(
        r'^factory/forwarder/(?P<pk>\d+)/toggle/$',
        StaffStreamerReportForwarderToggleView.as_view(),
        name='streamer-report-forwarder-toggle'
    ),
]
