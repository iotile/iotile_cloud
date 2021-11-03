from django.urls import path

from .views import *

app_name = 'physicaldevice'

urlpatterns = [
    path('', DeviceListView.as_view(), name='list'),
    path('<int:pk>/', DeviceDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', DeviceUpdateView.as_view(), name='edit'),
    path('<int:pk>/move/', DeviceMoveView.as_view(), name='move'),
    path('<int:pk>/reset/', DeviceResetView.as_view(), name='reset'),
    path('<int:pk>/trim/', DeviceTrimView.as_view(), name='trim'),
    path('<int:pk>/trim/mask/', DeviceTrimByMaskView.as_view(), name='trim-by-mask'),
    path('<int:pk>/trim/confirm/', DeviceTrimConfirmView.as_view(), name='trim-confirm'),
    path('<int:pk>/mask/', DeviceMaskView.as_view(), name='mask'),
    path('<int:pk>/property/', DevicePropertyView.as_view(), name='property'),
    path('<int:pk>/upload-events/', DeviceUploadEventsView.as_view(), name='upload-event'),
    path('<int:pk>/analytics/schedule/', DeviceGeneratedUserReportScheduleView.as_view(), name='analytics-schedule'),
    path('<int:pk>/filter/logs/clear/', DeviceFilterLogsClearView.as_view(), name='filter-logs-clear'),
    path('<int:pk>/health/status/', DeviceHealthStatusView.as_view(), name='health-status'),
    path('<int:pk>/health/settings/', SeviceStatusSettingsView.as_view(), name='health-settings'),
]
