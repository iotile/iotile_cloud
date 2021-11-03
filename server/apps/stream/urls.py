from django.urls import re_path

from .views import *

app_name = 'stream'

urlpatterns = [
    re_path(r'^(?P<slug>[sS]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}--[a-fA-F0-9]{4})/data-table/$',
            StreamIdDataTableView.as_view(), name='streamid-data-table'),
    re_path(r'^(?P<slug>[sS]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}--[a-fA-F0-9]{4})/event-table/$',
            StreamIdEventTableView.as_view(), name='streamid-event-table'),
    re_path(r'^(?P<slug>[sS]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}--[a-fA-F0-9]{4})/disable/$',
            StreamIdDisableUpdateView.as_view(), name='streamid-disable'),
    re_path(r'^(?P<slug>[sS]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}--[a-fA-F0-9]{4})/mdo/$',
            StreamIdMdoUpdateView.as_view(), name='streamid-mdo'),
    re_path(r'^(?P<slug>[sS]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}--[a-fA-F0-9]{4})/data-delete/$',
            UserStreamDataDeleteView.as_view(), name='stream-data-delete'),
    re_path(r'^(?P<slug>[sS]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}--[a-fA-F0-9]{4})/data-delete/confirm/$',
            UserStreamDataDeleteConfirmView.as_view(), name='stream-data-delete-confirm'),
]
