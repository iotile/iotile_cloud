from django.urls import include, path

from rest_framework import routers

from apps.authentication.api_views import AccountViewSet
from apps.component.api_views import APIComponentViewSet
from apps.configattribute.api_views import *
from apps.configattribute.api_views import APIConfigAttributeNameViewSet, APIConfigAttributeViewSet
from apps.datablock.api_views import APIDataBlockViewSet
from apps.deviceauth.api_views import APICreateDeviceKeyViewSet
from apps.devicelocation.api_views import APIDeviceLocationViewSet
from apps.devicescript.api_views import APIDeviceScriptViewSet
from apps.devicetemplate.api_views import APIDeviceTemplateViewSet
from apps.fleet.api_views import APIFleetViewSet
from apps.main.api_views import APIDbStatsViewSet, APIServerInfoViewSet
from apps.org.api_views import APIOrgViewSet
from apps.ota.api_views import *
from apps.physicaldevice.api_views import APIDeviceViewSet
from apps.project.api_views import APIProjectViewSet
from apps.projecttemplate.api_views import APIProjectTemplateViewSet
from apps.property.api_views import APIGenericPropertyViewSet, APIPropertyTemplateViewSet
from apps.report.api_views import APIReportSummaryGenerationViewSet
from apps.sensorgraph.api_views import APISensorGraphViewSet
from apps.stream.api_views import APIStreamIdViewSet, APIStreamVariableViewSet
from apps.streamdata.api_views import APIStreamDataFrameViewSet, APIStreamDataViewSet
from apps.streamer.api_views import APIStreamerReportUploadView, APIStreamerViewSet
from apps.streamevent.api_views import APIStreamEventDataViewSet
from apps.streamfilter.api_views import APIStreamFilterViewSet
from apps.streamnote.api_views import APIStreamNoteViewSet
from apps.vartype.api_views import APIVarTypeViewSet

public_api = routers.DefaultRouter()
public_api.register(r'org', APIOrgViewSet)
public_api.register(r'project', APIProjectViewSet)
public_api.register(r'device', APIDeviceViewSet)
public_api.register(r'datablock', APIDataBlockViewSet)
public_api.register(r'variable', APIStreamVariableViewSet)
public_api.register(r'stream', APIStreamIdViewSet)
public_api.register(r'data', APIStreamDataViewSet)
public_api.register(r'event', APIStreamEventDataViewSet)
public_api.register(r'note', APIStreamNoteViewSet)
public_api.register(r'location', APIDeviceLocationViewSet)
public_api.register(r'fleet', APIFleetViewSet, 'fleet')
public_api.register(r'property', APIGenericPropertyViewSet, 'property')
public_api.register(r'config/name', APIConfigAttributeNameViewSet)
public_api.register(r'config/attr', APIConfigAttributeViewSet)
public_api.register(r'streamer/report', APIStreamerReportUploadView, 'streamerreport')
public_api.register(r'streamer', APIStreamerViewSet)
public_api.register(r'vartype', APIVarTypeViewSet)

# Application Specific


docs_urlpatterns = [

    path('api/v1/auth/', include('apps.authentication.api_urls')),
    path('api/v1/shipping/', include('apps.verticals.shipping.api_urls')),
    path('api/v1/', include(public_api.urls)),
    path('api/v1/report/summary/', APIReportSummaryGenerationViewSet.as_view(), name='api--report-summary'),
]
