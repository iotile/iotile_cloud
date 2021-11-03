from django.contrib import admin
from .models import *

class ConfigAttributeNameAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'tags', )
    exclude = ['created_by', ]
    readonly_fields = ('created_by', 'created_on')
    search_fields = ['name', 'tags']
    raw_id_fields = ('created_by', )

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


class ConfigAttributeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'target', )
    exclude = ['updated_by', ]
    readonly_fields = ('updated_by', 'updated_on')
    search_fields = ['target']
    raw_id_fields = ('updated_by', )

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        obj.save()


"""
Register Admin Pages
"""
admin.site.register(ConfigAttributeName, ConfigAttributeNameAdmin)
admin.site.register(ConfigAttribute, ConfigAttributeAdmin)
