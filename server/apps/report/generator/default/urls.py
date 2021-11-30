from django.urls import path

from .views import (
    DefaultReportConfigureView, DefaultReportDefaultStep1View, DefaultReportDefaultStep2View, DefaultReportGenerateView,
)

app_name='report.generator.default'

urlpatterns = [
    path('configure/', DefaultReportConfigureView.as_view(), name='configure'),
    path('step1/', DefaultReportDefaultStep1View.as_view(), name='step1'),
    path('step2/', DefaultReportDefaultStep2View.as_view(), name='step2'),
    path('generate/', DefaultReportGenerateView.as_view(), name='generate'),
]
