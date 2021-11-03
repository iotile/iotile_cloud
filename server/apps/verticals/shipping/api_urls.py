from django.conf.urls import *

from .api_views import APIShippingArchiveQualitySummaryReportViewSet, APIShippingTripStatusReportViewSet

urlpatterns = [
    url(r'^org/quality/summary/(?P<org_slug>[^/]+)/$',
        APIShippingArchiveQualitySummaryReportViewSet.as_view(),
        name='api-org-quality-summary'),
    url(r'^project/status/(?P<project_slug>[pP]--[a-fA-F0-9]{4}-[a-fA-F0-9]{4})/$',
        APIShippingTripStatusReportViewSet.as_view(),
        name='api-project-trip-status'),
]
