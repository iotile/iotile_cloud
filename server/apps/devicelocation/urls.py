from django.urls import re_path

from .views import DeviceLocationView

app_name = 'devicelocation'

urlpatterns = [
    re_path(r'^(?P<slug>[dDbB]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/$',
            DeviceLocationView.as_view(), name='map'),
]
