"""
V1 API Router
"""
from rest_framework import routers

from apps.authentication.api_views import AccountViewSet
from apps.component.api_views import APIComponentViewSet
from apps.configattribute.api_views import APIConfigAttributeNameViewSet, APIConfigAttributeViewSet
from apps.datablock.api_views import APIDataBlockViewSet
from apps.deviceauth.api_views import APICreateDeviceKeyViewSet
from apps.devicelocation.api_views import APIDeviceLocationViewSet
from apps.devicescript.api_views import APIDeviceScriptViewSet
from apps.devicetemplate.api_views import APIDeviceTemplateViewSet
from apps.fleet.api_views import APIFleetViewSet
from apps.org.api_views import APIOrgViewSet
from apps.orgtemplate.api_views import APIOrgTemplateViewSet
from apps.ota.api_views import APIDeploymentActionViewSet, APIDeploymentRequestViewSet, APIDeviceVersionViewSet
from apps.physicaldevice.api_views import APIDeviceViewSet, APIManufacturingDataViewSet
from apps.project.api_views import APIProjectViewSet
from apps.projecttemplate.api_views import APIProjectTemplateViewSet
from apps.property.api_views import APIGenericPropertyViewSet, APIPropertyTemplateViewSet
from apps.report.api_views import APIGeneratedUserReportViewSet
from apps.sensorgraph.api_views import (
    APIDisplayWidgetTemplateViewSet, APISensorGraphViewSet, APIVariableTemplateViewSet,
)
from apps.stream.api_views import APIStreamIdViewSet, APIStreamVariableViewSet
from apps.streamalias.api_views import APIStreamAliasTapViewSet, APIStreamAliasViewSet
from apps.streamdata.api_views import APIStreamDataViewSet
from apps.streamer.api_views import APIStreamerReportUploadView, APIStreamerViewSet
from apps.streamevent.api_views import APIStreamEventDataViewSet, APIStreamEventUploadViewSet
from apps.streamfilter.api_views import APIStreamFilterViewSet
from apps.streamnote.api_views import APIStreamNoteViewSet
from apps.vartype.api_views import APIVarTypeViewSet
from apps.verticals.shipping.api_views import APIShippingTripViewSet

# Rest APIs
# =========
v1_api_router = routers.DefaultRouter()
v1_api_router.register(r'account', AccountViewSet)
v1_api_router.register(r'org', APIOrgViewSet)
v1_api_router.register(r'fleet', APIFleetViewSet, 'fleet')
v1_api_router.register(r'project', APIProjectViewSet)
v1_api_router.register(r'device', APIDeviceViewSet)
v1_api_router.register(r'datablock', APIDataBlockViewSet)
v1_api_router.register(r'variable', APIStreamVariableViewSet)
v1_api_router.register(r'stream', APIStreamIdViewSet)
v1_api_router.register(r'data', APIStreamDataViewSet)
v1_api_router.register(r'event/upload', APIStreamEventUploadViewSet, 'eventupload')
v1_api_router.register(r'event', APIStreamEventDataViewSet)
v1_api_router.register(r'note', APIStreamNoteViewSet)
v1_api_router.register(r'location', APIDeviceLocationViewSet)
v1_api_router.register(r'property', APIGenericPropertyViewSet, 'property')
v1_api_router.register(r'filter', APIStreamFilterViewSet)
v1_api_router.register(r'alias', APIStreamAliasViewSet)
v1_api_router.register(r'tap', APIStreamAliasTapViewSet)
v1_api_router.register(r'report/generated', APIGeneratedUserReportViewSet, 'generateduserreport')
v1_api_router.register(r'streamer/report', APIStreamerReportUploadView, 'streamerreport')
v1_api_router.register(r'streamer', APIStreamerViewSet)
v1_api_router.register(r'component', APIComponentViewSet)
v1_api_router.register(r'dt', APIDeviceTemplateViewSet)
v1_api_router.register(r'ot', APIOrgTemplateViewSet)
v1_api_router.register(r'pt', APIProjectTemplateViewSet)
v1_api_router.register(r'sg', APISensorGraphViewSet)
v1_api_router.register(r'vartemplate', APIVariableTemplateViewSet)
v1_api_router.register(r'widget', APIDisplayWidgetTemplateViewSet)
v1_api_router.register(r'vartype', APIVarTypeViewSet)
v1_api_router.register(r'config/name', APIConfigAttributeNameViewSet)
v1_api_router.register(r'config/attr', APIConfigAttributeViewSet)
v1_api_router.register(r'propertytemplate', APIPropertyTemplateViewSet, 'propertytemplate')
v1_api_router.register(r'key', APICreateDeviceKeyViewSet, 'key')
v1_api_router.register(r'ota/script', APIDeviceScriptViewSet)
v1_api_router.register(r'ota/request', APIDeploymentRequestViewSet)
v1_api_router.register(r'ota/action', APIDeploymentActionViewSet)
v1_api_router.register(r'ota/version', APIDeviceVersionViewSet)
v1_api_router.register(r'production/device', APIManufacturingDataViewSet, 'manufacturingdata')

# Application Specific:
# ---------------------

# Shipping
v1_api_router.register(r'shipping/trip', APIShippingTripViewSet, 'shipping-trip')
