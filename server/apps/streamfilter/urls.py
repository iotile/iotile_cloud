from django.urls import re_path

from .views import *

app_name = 'streamfilter'

urlpatterns = [
    re_path(r'^(?P<slug>[\w-]+)/detail/$', StreamFilterDetailView.as_view(), name='detail'),
    re_path(r'^(?P<slug>[\w-]+)/delete/$', StreamFilterDeleteView.as_view(), name='delete'),
    re_path(r'^(?P<slug>[\w-]+)/reset/$', StreamFilterResetView.as_view(), name='reset'),
    re_path(r'^(?P<slug>[\w-]+)/state/create/$', StateCreateView.as_view(), name='state-create'),
    re_path(r'^(?P<slug>[\w-]+)/transition/create/$', TransitionCreateView.as_view(), name='transition-create'),
    re_path(r'^(?P<filter_slug>[\w-]+)/state/(?P<slug>[\w-]+)/delete/$', StateDeleteView.as_view(), name='state-delete'),
    re_path(r'^(?P<filter_slug>[\w-]+)/state/(?P<slug>[\w-]+)/detail/$', StateDetailView.as_view(), name='state-detail'),
    re_path(r'^(?P<filter_slug>[\w-]+)/(?P<slug>[\w-]+)/action-create/(?P<type>[\w-]+)/$', StreamFilterActionCreateView.as_view(), name='action-create'),
    re_path(r'^(?P<filter_slug>[\w-]+)/(?P<slug>[\w-]+)/action-create/$', StreamFilterActionTypeCreateView.as_view(), name='action-create-type'),
    re_path(r'^(?P<filter_slug>[\w-]+)/action/(?P<pk>\d+)/edit/$', StreamFilterActionEditView.as_view(), name='action-edit'),
    re_path(r'^(?P<filter_slug>[\w-]+)/action/(?P<pk>\d+)/delete/$', StreamFilterActionDeleteView.as_view(), name='action-delete'),
    re_path(r'^(?P<filter_slug>[\w-]+)/transition/(?P<pk>[\w-]+)/delete/$', TransitionDeleteView.as_view(), name='transition-delete'),
    re_path(r'^(?P<filter_slug>[\w-]+)/transition/(?P<pk>[\w-]+)/edit/$', TransitionEditView.as_view(), name='transition-edit'),
    re_path(r'^(?P<filter_slug>[\w-]+)/transition/(?P<pk>[\w-]+)/trigger/add/$', TriggerAddView.as_view(), name='trigger-add'),
    re_path(r'^(?P<filter_slug>[\w-]+)/trigger/(?P<pk>\d+)/delete/$', TriggerDeleteView.as_view(), name='trigger-delete'),
    re_path(r'^(?P<filter_slug>[\w-]+)/trigger/(?P<pk>\d+)/edit/$', TriggerEditView.as_view(), name='trigger-edit'),
]
