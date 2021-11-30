from django.urls import path, re_path

from .views import *

app_name = 'invitation'

urlpatterns = [
     path('invite/', InvitationSendView.as_view(), name='invite'),
     re_path(r'^(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/accept/$',
             InvitationAcceptView.as_view(), name='accept'),
     re_path(r'^(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/resend/$',
             InvitationResendView.as_view(), name='resend'),
     re_path(r'^(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/delete/$',
             InvitationDeleteView.as_view(), name='delete'),
]
