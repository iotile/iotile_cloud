from django.contrib import admin

from .models import *

class GenericPropertyAdmin(admin.ModelAdmin):
    list_display = ('id', 'target', 'name', 'str_value', 'is_system', )
    exclude = ['created_by',]
    readonly_fields = ('created_by', 'created_on')
    search_fields = ['name', 'target',]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


class GenericPropertyOrgTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'org', 'name', 'type', )
    exclude = ['created_by',]
    readonly_fields = ('created_by', 'created_on')
    search_fields = ['name', 'org__slug']

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


class GenericPropertyOrgEnumAdmin(admin.ModelAdmin):
    list_display = ('id', 'org', 'template', 'value' )
    exclude = ['created_by',]
    readonly_fields = ('created_by', 'created_on', 'org')
    search_fields = ['org', 'property', 'value']

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.org = obj.template.org
        obj.save()


"""
Register Admin Pages
"""
admin.site.register(GenericProperty, GenericPropertyAdmin)
admin.site.register(GenericPropertyOrgTemplate, GenericPropertyOrgTemplateAdmin)
admin.site.register(GenericPropertyOrgEnum, GenericPropertyOrgEnumAdmin)
