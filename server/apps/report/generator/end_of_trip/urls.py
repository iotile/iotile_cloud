from django.urls import path

from .views import EndOfTripReportConfigureView, EndOfTripReportGenerateView

app_name='report.generator.end_of_trip'

urlpatterns = [
    path('configure/', EndOfTripReportConfigureView.as_view(), name='configure'),
    path('generate/', EndOfTripReportGenerateView.as_view(), name='generate'),
]
