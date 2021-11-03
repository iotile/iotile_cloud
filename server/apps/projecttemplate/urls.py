from django.urls import path

from .views import *

app_name = 'projecttemplate'

urlpatterns = [
    path('', ProjectTemplateListView.as_view(), name='list'),
    path('add/', ProjectTemplateCreateView.as_view(), name='create'),
    path('<slug:slug>/', ProjectTemplateDetailView.as_view(), name='detail'),
]
