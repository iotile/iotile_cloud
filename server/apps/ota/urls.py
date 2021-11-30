from django.urls import include, path

from .views import *

app_name = 'ota'

urlpatterns = [
    path('device-file/', include('apps.devicefile.urls', namespace='file')),
    path('<slug:org_slug>/', OtaIndexView.as_view(), name='index'),
    path('<slug:org_slug>/script/', include('apps.devicescript.urls', namespace='script')),
    path('<slug:org_slug>/request/', DeploymentRequestListView.as_view(), name='request-list'),
    path('<slug:org_slug>/request/add/', DeploymentRequestCreateView.as_view(), name='request-create'),
    path('<slug:org_slug>/request/<int:pk>/', DeploymentRequestDetailView.as_view(), name='request-detail'),
    path('<slug:org_slug>/request/<int:pk>/edit/', DeploymentRequestUpdateView.as_view(), name='request-edit'),
    path('<slug:org_slug>/request/<int:pk>/release/', DeploymentRequestReleaseView.as_view(),
         name='request-release'),
    path('<slug:org_slug>/request/<int:pk>/complete/', DeploymentRequestCompleteView.as_view(),
         name='request-complete'),
]