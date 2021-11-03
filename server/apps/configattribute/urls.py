from django.urls import path

from .views import ConfigAttributeEditView

app_name = 'configattribute'

urlpatterns = [
    path('<int:pk>/edit/', ConfigAttributeEditView.as_view(), name='edit'),
]
