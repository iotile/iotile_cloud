from django.urls import path

from .views import (
    AnalyticsReportConfigureView,
    AnalyticsReportGenerateView,
)

app_name='report.generator.analytics'

urlpatterns = [
    path('configure/', AnalyticsReportConfigureView.as_view(), name='configure'),
    path('generate/', AnalyticsReportGenerateView.as_view(), name='generate'),
]
