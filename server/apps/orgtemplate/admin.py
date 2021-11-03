from django.contrib import admin
from .models import *

class OrgTemplateAdmin(admin.ModelAdmin):
    list_display = ('slug', 'name', 'version', 'active', )
    exclude = ['created_by', 'slug', ]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


"""
Register Admin Pages
"""
admin.site.register(OrgTemplate, OrgTemplateAdmin)
