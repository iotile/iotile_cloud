from django.urls import path, re_path
from django.conf import settings

from .views import *

app_name = 'datablock'

urlpatterns = [
    path('', DataBlockListView.as_view(), name='list'),
    re_path(r'^add/(?P<device_slug>[dD]--[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4})/$',
            DataBlockCreateView.as_view(), name='add'),
    re_path(r'^(?P<slug>[bB]--[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4})/$',
            DataBlockDetailView.as_view(), name='detail'),
    re_path(r'^(?P<slug>[bB]--[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4})/edit/$',
            DataBlockEditView.as_view(), name='edit'),
    re_path(r'^(?P<slug>[bB]--[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4})/delete/$',
            DataBlockDeleteConfirmView.as_view(), name='delete'),
    re_path(r'^(?P<slug>[bB]--[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4})/analytics/schedule/$',
            DataBlockGeneratedUserReportScheduleView.as_view(), name='analytics-schedule'),
    re_path(r'^(?P<slug>[bB]--[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4})/mask/$',
            DataBlockMaskView.as_view(), name='mask'),
]


