from django.urls import path

from .views import *

app_name = 's3file'

urlpatterns = [
     # path('upload/', S3FileUploadView.as_view(), name='upload'),
     path('s3/signature/', S3FileUploadSignView.as_view(), name='upload-signee'),
     path('s3/success/', S3FileUploadSuccessEndpointView.as_view(), name='upload-success'),
     path('<uuid:pk>/', S3FileDetailView.as_view(), name='detail'),
]
