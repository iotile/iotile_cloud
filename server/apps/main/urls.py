from django.conf import settings
from django.urls import include, path, re_path
from django.views.generic.base import RedirectView

from .views import *

FAVICON_PATH = getattr(settings, 'FAVICON_PATH', '{}favicon.ico'.format(settings.STATIC_URL))

urlpatterns = [
    path('', HomeIndexView.as_view(), name='home'),
    path('onboard1', OnBoardOrgStepView.as_view(), name='onboard-step-org'),
    path('onboard1/done', OnBoardOrgDoneStepView.as_view(),
         name='onboard-step-org-done'),
    path('onboard2', OnBoardDeviceStepView.as_view(), name='onboard-step-device'),
    path('onboard3', OnBoardMobileAppStepView.as_view(),
         name='onboard-step-mobile'),
    path('onboard4', OnBoardDeviceClaimStepView.as_view(),
         name='onboard-step-claim'),
    path('about/', AboutView.as_view(), name='about'),
    # ---------------------------------
    re_path(r'^favicon\.ico$', RedirectView.as_view(
            url=FAVICON_PATH, permanent=True), name='favicon'),
    path('jsi18n', i18n_javascript),
    path('admin/jsi18n', i18n_javascript),
    path('i18n/', include('django.conf.urls.i18n')),
    path('robots.txt', RobotView.as_view()),
    path('crossdomain.xml', CrossDomainView.as_view()),
]
