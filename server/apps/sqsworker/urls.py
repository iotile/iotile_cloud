from django.urls import path, re_path

from .views import *

app_name = 'sqsworker'

urlpatterns = [
    path('', WorkerStatusView.as_view(), name='home'),
    path('action-stats/', ActionStatsView.as_view(), name='action-stats'),
    re_path(r'^(?P<uuid>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})$',
            WorkerDetailView.as_view(), name='detail'),
    path('schedule/', WorkerScheduleView.as_view(), name='schedule'),
    path('cleanup/', WorkerCleanupAllView.as_view(), name='cleanup-all'),
    re_path(r'^(?P<uuid>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/cleanup$',
            WorkerCleanupView.as_view(), name='cleanup'),
    re_path(r'^action/(?P<action_name>[\w-]+)$', WorkerActionDetailView.as_view(), name='action-detail'),
]