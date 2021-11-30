from django.urls import include, path, re_path

from .views import *

app_name = 'org'

urlpatterns = [
    # OrgMembership
    re_path(r'^member/(?P<pk>[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/edit/$',
            OrgMembershipEditView.as_view(), name='member-edit'),
    # Org
    path('add/', OrgCreateView.as_view(), name='create'),
    path('<slug:slug>/', OrgDetailView.as_view(), name='detail'),
    path('<slug:slug>/edit/', OrgEditView.as_view(), name='edit'),
    path('<slug:slug>/users/', OrgMembersView.as_view(), name='members'),
    path('<slug:slug>/users/export/csv/', OrgMembersCsvView.as_view(), name='export-member-csv'),
    path('<slug:slug>/member/message/', OrgMembershipMessageView.as_view(), name='member-message'),
    path('<slug:slug>/roles/', OrgRolesView.as_view(), name='roles'),
    path('<slug:slug>/search/', OrgSearchView.as_view(), name='search'),
    path('<slug:slug>/apikeys/', OrgAPIKeysView.as_view(), name='apikeys'),
    path('<slug:slug>/apikeys/add/', OrgAPIKeyCreateView.as_view(), name='apikey-add'),
    path('<slug:slug>/image/upload/', OrgS3FileUploadView.as_view(), name='upload-image'),
    path('<slug:slug>/image/success/',
         OrgS3FileUploadSuccessEndpointView.as_view(), name='upload-image-success'),
    path('<slug:org_slug>/invitation/', include('apps.invitation.urls', namespace='invitation')),
    path('<slug:org_slug>/project/', include('apps.project.urls', namespace='project')),
    path('<slug:org_slug>/page/', include('apps.widget.urls', namespace='page')),
    path('<slug:org_slug>/block/', include('apps.datablock.urls', namespace='datablock')),
    path('<slug:org_slug>/report/', include('apps.report.urls', namespace='report')),
    path('<slug:org_slug>/fleet/', include('apps.fleet.urls', namespace='fleet')),
]
