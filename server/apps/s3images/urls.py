from django.urls import path, re_path

from .views import *

app_name = 's3images'

urlpatterns = [
     path('upload/', S3ImageUploadView.as_view(), name='upload'),
     path('s3/signature/', S3ImageUploadSignView.as_view(), name='upload-signee'),
     path('s3/success/', S3ImageUploadSuccessEndpointView.as_view(), name='upload-success'),
     re_path(r'^(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/$',
             S3ImageDetailView.as_view(), name='detail'),
]