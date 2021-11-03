from django.urls import path

from .views import *

app_name = 'orgtemplate'

urlpatterns = [
    path('', OrgTemplateListView.as_view(), name='list'),
    path('add/', OrgTemplateCreateView.as_view(), name='create'),
    path('<slug:slug>/', OrgTemplateDetailView.as_view(), name='detail'),
]
