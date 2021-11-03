from django.urls import re_path

from .views import *

app_name = 'stream'

urlpatterns = [
     re_path(r'^(?P<slug>[pPtTvV]+--[a-f0-9]{4}-[a-f0-9]{4}--[a-f0-9]{4})/$',
             StreamVariableDetailView.as_view(), name='detail'),
     re_path(r'^(?P<slug>[pPtTvV]+--[a-f0-9]{4}-[a-f0-9]{4}--[a-f0-9]{4})/edit/$',
             StreamVariableUpdateView.as_view(), name='update'),
     re_path(r'^(?P<slug>[pPtTvV]+--[a-f0-9]{4}-[a-f0-9]{4}--[a-f0-9]{4})/units/$',
             StreamVariableUnitsView.as_view(), name='units'),
     re_path(r'^(?P<slug>[pPtTvV]+--[a-f0-9]{4}-[a-f0-9]{4}--[a-f0-9]{4})/delete/$',
             StreamVariableDeleteView.as_view(), name='delete'),
]
