from django.contrib import admin
from .models import *

class DeviceKeyAdmin(admin.ModelAdmin):
    list_display = ('slug', 'type', 'downloadable', )
    search_fields = ['slug', 'type', ]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


"""
Register Admin Pages
"""
admin.site.register(DeviceKey, DeviceKeyAdmin)
