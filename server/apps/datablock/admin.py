from django.contrib import admin
from .models import *

class DataBlockAdmin(admin.ModelAdmin):
    list_display = ('id', 'slug', 'org', 'device', 'block', )
    exclude = ['created_by', 'org',]
    readonly_fields = ('formatted_gid', 'slug', 'created_by', 'created_on')
    search_fields = ['slug', 'title']

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        if obj.device and obj.device.project:
            obj.org = obj.device.project.org
        else:
            obj.org = None
        obj.save()

    def get_form(self, request, obj=None, **kwargs):
        form = super(DataBlockAdmin, self).get_form(request, obj, **kwargs)
        return form


"""
Register Admin Pages
"""
admin.site.register(DataBlock, DataBlockAdmin)

