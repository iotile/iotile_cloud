from django.conf.urls import *

from .views import *

app_name = 'devicetemplate'

urlpatterns = [
    url(r'^$', ProductListView.as_view(), name='list'),
    url(r'^add/$', ProductCreateView.as_view(), name='create'),
    url(r'^(?P<slug>[^/]+)/$', ProductDetailView.as_view(), name='detail'),
    url(r'^(?P<slug>[^/]+)/edit/$', ProductUpdateView.as_view(), name='edit'),
    url(r'^(?P<slug>[^/]+)/component/add/$', AddComponentToProductView.as_view(), name='component-add'),

    url(r'^(?P<slug>[^/]+)/image/upload/$',
        ProductS3ImageUploadView.as_view(), name='upload-image'),
    url(r'^(?P<slug>[^/]+)/image/success/$',
        ProductS3ImageUploadSuccessEndpointView.as_view(), name='upload-image-success'),
    url(r'^(?P<template_slug>[^/]+)/image/(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/delete/$',
        ProductS3ImageDeleteView.as_view(), name='image-delete'),
    url(r'^(?P<template_slug>[^/]+)/image/(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/title/$',
        ProductS3ImageTitleUpdateView.as_view(), name='image-title-edit'),

]
