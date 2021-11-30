from rest_framework_api_key.admin import APIKeyModelAdmin

from django.contrib import admin

from .forms import OrgDomainAdminForm, OrgMembershipAdminForm
from .models import *
from .roles import ORG_ROLE_CHOICES, ORG_ROLE_PERMISSIONS


class OrgAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug')
    exclude = ['created_by', 'slug']
    readonly_fields = ('created_by', 'created_on')
    search_fields = ['name',]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()
        if not OrgMembership.objects.filter(user=request.user, org=obj).exists():
            OrgMembership.objects.create(user=request.user, org=obj)

    def get_queryset(self, request):
        qs = super(OrgAdmin, self).get_queryset(request)
        return qs.order_by('slug')


class OrgMembershipAdmin(admin.ModelAdmin):
    role = models.CharField(max_length=2, choices=ORG_ROLE_CHOICES)
    list_display = ('id', 'user', 'org', 'role', 'is_active', )
    raw_id_fields = ('user', )
    exclude = ['permissions', ]
    search_fields = ['user__username', 'org__slug',]
    readonly_fields = ('permissions', 'is_org_admin')
    form = OrgMembershipAdminForm

    def get_form(self, request, obj=None, **kwargs):
        form = super(OrgMembershipAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['org'].queryset = Org.objects.all().order_by('name')
        return form

    def save_model(self, request, obj, form, change):
        obj.permissions = ORG_ROLE_PERMISSIONS[obj.role]
        obj.is_org_admin = obj.role in ['a0', 'a1']
        obj.save()


class OrgDomainAdmin(admin.ModelAdmin):
    default_role = models.CharField(max_length=64, choices=ORG_ROLE_CHOICES)
    list_display = ('id', 'name', 'org', 'default_role', 'verified')
    search_fields = ['name', 'org__slug',]
    form = OrgDomainAdminForm

    def get_form(self, request, obj=None, **kwargs):
        form = super(OrgDomainAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['org'].queryset = Org.objects.all().order_by('name')
        return form


class AuthAPIKeyModelAdmin(APIKeyModelAdmin):
    list_display = [*APIKeyModelAdmin.list_display, 'org',]
    search_fields = [*APIKeyModelAdmin.search_fields, 'org__slug',]


"""
Register Admin Pages
"""
admin.site.register(Org, OrgAdmin)
admin.site.register(OrgMembership, OrgMembershipAdmin)
admin.site.register(OrgDomain, OrgDomainAdmin)
admin.site.register(AuthAPIKey, AuthAPIKeyModelAdmin)
