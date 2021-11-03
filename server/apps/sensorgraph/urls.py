from django.urls import path

from .views import (
    SensorGraphListView, SensorGraphCreateView, SensorGraphDetailView,
    SensorGraphUpdateView, SensorGraphEditUiExtraView, SensorGraphEditSgfView,
    SensorGraphSGFUploadView, SensorGraphSGFUploadSuccessEndpointView
)

app_name = 'sensorgraph'

urlpatterns = [
    path('', SensorGraphListView.as_view(), name='list'),
    path('add/', SensorGraphCreateView.as_view(), name='create'),
    path('<slug:slug>)/', SensorGraphDetailView.as_view(), name='detail'),
    path('<slug:slug>/edit/', SensorGraphUpdateView.as_view(), name='edit'),
    path('<slug:slug>/ui_extra/', SensorGraphEditUiExtraView.as_view(), name='edit-ui-extra'),
    path('<slug:slug>/sgf/', SensorGraphEditSgfView.as_view(), name='edit-sgf'),
    path('<slug:slug>/file/upload/', SensorGraphSGFUploadView.as_view(), name='sgf-upload'),
    path('<slug:slug>/file/success/',
        SensorGraphSGFUploadSuccessEndpointView.as_view(), name='sgf-upload-success'),
]
