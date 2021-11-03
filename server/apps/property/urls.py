from django.urls import path

from .views import *

app_name = 'property'

urlpatterns = [
    path('<slug:target_slug>/add/', GenericPropertyCreateView.as_view(), name='add'),
    path('<slug:target_slug>/edit/<int:pk>/', GenericPropertyUpdateView.as_view(), name='edit'),
    path('<slug:target_slug>/delete/<int:pk>/', GenericPropertyDeleteView.as_view(), name='delete'),

    path('template/<slug:org_slug>/', PropertyTemplateListView.as_view(), name='template-list'),
    path('template/<slug:org_slug>/enum/add/',
         PropertyTemplateEnumCreateView.as_view(), name='template-enum-add'),
    path('template/<slug:org_slug>/<int:template_pk>/enum/delete/<int:pk>/',
         PropertyTemplateEnumDeleteView.as_view(), name='template-enum-delete'),
    path('template/<slug:org_slug>/<int:pk>/',
         PropertyTemplateEnumListView.as_view(), name='template-detail'),
]
