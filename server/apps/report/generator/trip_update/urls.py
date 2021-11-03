from django.urls import path

from .views import (
    EndOfTripReportConfigureView,
    EndOfTripReportGenerateView,
)

app_name='report.generator.trip_update'

urlpatterns = [
    path('configure/', EndOfTripReportConfigureView.as_view(), name='configure'),
    path('generate/', EndOfTripReportGenerateView.as_view(), name='generate'),
]
