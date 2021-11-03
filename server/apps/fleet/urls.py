from django.urls import path, re_path

from .views import *

app_name = 'fleet'

urlpatterns = [
    path('', FleetListView.as_view(), name='list'),
    path('add/', FleetCreateView.as_view(), name='add'),
    re_path(r'^(?P<slug>[gG]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/$', FleetDetailView.as_view(), name='detail'),
    re_path(r'^(?P<slug>[gG]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/edit/$', FleetUpdateView.as_view(), name='edit'),
    re_path(r'^(?P<slug>[gG]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/member/add/$',
            FleetMemberAddView.as_view(), name='member-add'),
    re_path(r'^(?P<slug>[gG]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/member/(?P<pk>\d+)/$',
            FleetMemberEditView.as_view(), name='member-edit'),
    re_path(r'^(?P<slug>[gG]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/member/(?P<pk>\d+)/delete/$',
            FleetMemberDeleteView.as_view(), name='member-delete'),
]
