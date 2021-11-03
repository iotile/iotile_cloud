from django.urls import path, re_path, include

from apps.stream.views import StreamVariableListView, StreamVariableCreateView
from .views import *

app_name = 'project'

urlpatterns = [
    path('new/', ProjectCreateFromTemplateView.as_view(), name='new'),
    path('add/', ProjectCreateView.as_view(), name='create'),
    re_path(r'^(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/$',
            ProjectDetailView.as_view(), name='detail'),
    re_path(r'^(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/edit/$',
            ProjectUpdateView.as_view(), name='edit'),
    re_path(r'^(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/delete/$',
            ProjectDeleteView.as_view(), name='delete'),

    re_path(r'^(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/clone/$',
            ProjectCloneView.as_view(), name='clone'),

    re_path(r'^(?P<project_id>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/device/',
            include('apps.physicaldevice.urls', namespace='device')),

    re_path(r'^(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/property/$',
            ProjectPropertyView.as_view(), name='property'),

    # Dashboard
    re_path(r'^(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/stream/$',
            DashboardStreamIdListView.as_view(), name='streamid-list'),
    re_path(r'^(?P<project_id>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/stream/',
            include('apps.stream.urls', namespace='stream')),

    # Project Variables
    re_path(r'^(?P<project_id>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/var/$', StreamVariableListView.as_view(), name='var-list'),
    re_path(r'^(?P<project_id>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/var/add/$',
            StreamVariableCreateView.as_view(), name='var-create'),

    # Stream Filters
    re_path(r'^(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/filter/add', ProjectStreamFilterCreateView.as_view(), name="filter-add"),

]
