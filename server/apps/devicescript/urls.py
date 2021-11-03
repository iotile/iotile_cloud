from django.urls import path, re_path

from .views import *

app_name = 'devicescript'

urlpatterns = [
    path('', DeviceScriptListView.as_view(), name='list'),
    path('add/', DeviceScriptCreateView.as_view(), name='create'),
    re_path(r'^(?P<slug>[zZ]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/$',
            DeviceScriptDetailView.as_view(), name='detail'),
    re_path(r'^(?P<slug>[zZ]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/edit/$',
            DeviceScriptUpdateView.as_view(), name='edit'),
    re_path(r'^(?P<slug>[zZ]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/release/$',
            DeviceScriptReleaseView.as_view(), name='release'),
    re_path(r'^(?P<slug>[zZ]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/file/upload/$',
            DeviceScriptS3FileUploadView.as_view(), name='upload'),
    re_path(r'^(?P<slug>[zZ]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/file/success/$',
            DeviceScriptS3FileUploadSuccessEndpointView.as_view(), name='upload-success'),
]
