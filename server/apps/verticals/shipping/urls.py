from django.urls import re_path

from .views import *

app_name = 'shipping'

urlpatterns = [
    re_path(r'^(?P<slug>[pP]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/status/$', ShippingProjectView.as_view(), name='project-status'),
    re_path(r'^(?P<slug>[pP]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/sxd/device/$', SxdDeviceFormView.as_view(), name='sxd-step-device'),
    re_path(r'^(?P<slug>[dD]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/sxd/properties/$', SxdPropertyFormView.as_view(), name='sxd-step-properties'),
    re_path(r'^(?P<slug>[dD]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/sxd/upload/$', ShippingSxdFileUploadView.as_view(), name='sxd-step-upload'),
    re_path(r'^(?P<slug>[dD]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/sxd/sign/$', ShippingSxdFileUploadSignView.as_view(), name='sxd-step-sign'),
    re_path(r'^(?P<slug>[dD]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/sxd/success/$', ShippingSxdFileUploadSuccessEndpointView.as_view(), name='sxd-step-upload-success'),
    re_path(r'^(?P<slug>[dD]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/trip/start/$', DeviceStartTripView.as_view(), name='start-trip'),
]
