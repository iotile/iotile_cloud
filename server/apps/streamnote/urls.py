from django.urls import path

from .views import *

app_name = 'streamnote'

urlpatterns = [
    path('<slug:slug>/', StreamNoteListView.as_view(), name='list'),
    path('<slug:slug>/add/', StreamNoteCreateView.as_view(), name='add'),
    path('<int:pk>/attachment/upload/', StreamNoteS3FileUploadView.as_view(), name='upload'),
    path('<int:pk>/attachment/success/',
        StreamNoteS3FileUploadSuccessEndpointView.as_view(), name='upload-success'),
    path('<int:pk>/attachment/sign/',
        StreamNoteS3FileUploadSignView.as_view(), name='upload-sign'),
]
