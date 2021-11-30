from django.contrib import admin

from .models import DeviceFile


class DeviceFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'tag', 'version', )


admin.site.register(DeviceFile, DeviceFileAdmin)

