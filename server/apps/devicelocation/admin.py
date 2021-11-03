from django.contrib import admin

from .models import *

class DeviceLocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'target_slug', 'timestamp', 'lat', 'lon', 'user')
    search_fields = ['target_slug', ]
    readonly_fields =  ['user', ]
    raw_id_fields = ('user', )

    def save_model(self, request, obj, form, change):
        obj.user = request.user
        obj.save()


"""
Register Admin Pages
"""
admin.site.register(DeviceLocation, DeviceLocationAdmin)