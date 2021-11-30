from django.urls import include, path

from .views import *

app_name = 'report'

urlpatterns = [
    path('', UserReportListView.as_view(), name='list'),
    path('add/', UserReportCreateView.as_view(), name='add'),
    path('<int:pk>/delete/', UserReportDeleteView.as_view(), name='delete'),
    path('<int:pk>/recipient/add/', UserReportAddRecipientView.as_view(), name='add-recipient'),
    path('<int:pk>/delete/', UserReportDeleteView.as_view(), name='delete'),
    # Default Extras
    path('<int:pk>/default/', include('apps.report.generator.default.urls', namespace='default')),
    path('<int:pk>/end_of_trip/', include('apps.report.generator.end_of_trip.urls', namespace='end_of_trip')),
    path('<int:pk>/analytics/', include('apps.report.generator.analytics.urls', namespace='analytics')),
    # Generated Reports
    path('generated/<uuid:pk>/',
         GeneratedUserReportDetailView.as_view(), name='generated-detail'),
    path('generated/<uuid:pk>/edit/',
         GeneratedUserReportEditView.as_view(), name='generated-edit'),
    path('generated/<uuid:pk>/delete/',
         GeneratedUserReportDeleteView.as_view(), name='generated-delete'),
]
