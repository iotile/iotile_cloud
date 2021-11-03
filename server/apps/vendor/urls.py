from django.urls import path

from .views import *

app_name = 'vendor'

urlpatterns = [
    path('<slug:slug>/', VendorIndexView.as_view(), name='home'),
    path('<slug:slug>/map/', VendorMapView.as_view(), name='map'),
    path('<slug:slug>/project/', VendorProjectListView.as_view(), name='project-list'),
    path('<slug:slug>/device/<int:pk>/', VendorDeviceDetailView.as_view(), name='device-detail'),
    path('<slug:slug>/dt/', VendorProductListView.as_view(), name='dt-list'),
    path('<slug:slug>/sg/matrix/', VendorSensorGraphMatrixView.as_view(), name='sg-matrix'),
    path('<slug:slug>/product/matrix/', VendorProductMatrixView.as_view(), name='product-matrix'),
]
