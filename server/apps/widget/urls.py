from django.urls import re_path

from .views import *

app_name = 'widget'

urlpatterns = [
    re_path(r'^(?P<slug>[dD]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/$',
            PageDeviceView.as_view(), name='device'),

]
