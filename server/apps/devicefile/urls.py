from django.urls import path

from .views import *

app_name = 'devicefile'

urlpatterns = [
    path('', DeviceFileListView.as_view(), name='list'),
    path('add/<slug:org_slug>/', DeviceFileCreateView.as_view(), name='create'),
    path('<slug:slug>/', DeviceFileDetailView.as_view(), name='detail'),
    path('<slug:slug>/edit/', DeviceFileUpdateView.as_view(), name='edit'),
    path('<slug:slug>/file/upload/', DeviceFileS3FileUploadView.as_view(), name='upload'),
    path('<slug:slug>/file/success/',
         DeviceFileS3FileUploadSuccessEndpointView.as_view(), name='upload-success'),
]
