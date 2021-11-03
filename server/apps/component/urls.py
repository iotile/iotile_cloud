from django.urls import path, re_path

from .views import *

app_name = 'component'

urlpatterns = [
    path('', ComponentListView.as_view(), name='list'),
    path('add/', ComponentCreateView.as_view(), name='create'),
    re_path(r'^(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/$',
            ComponentDetailView.as_view(), name='detail'),
    re_path(r'^(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/edit/$',
            ComponentUpdateView.as_view(), name='edit'),
    re_path(r'^(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/image/upload/$',
            ComponentS3ImageUploadView.as_view(), name='upload-image'),
    re_path(r'^(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/image/success/$',
            ComponentS3ImageUploadSuccessEndpointView.as_view(), name='upload-image-success'),
    re_path(r'^(?P<component_id>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/image/(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/delete/$',
            ComponentS3ImageDeleteView.as_view(), name='image-delete'),
    re_path(r'^(?P<component_id>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/image/(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/title/$',
            ComponentS3ImageTitleUpdateView.as_view(), name='image-title-edit'),

]
