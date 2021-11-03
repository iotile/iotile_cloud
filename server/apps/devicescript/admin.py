from django.contrib import admin
from .models import *

class DeviceScriptAdmin(admin.ModelAdmin):
    list_display = ('slug', 'released', 'version' )
    exclude = ['created_by', 'file', ]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

    def get_form(self, request, obj=None, **kwargs):
        form = super(DeviceScriptAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['org'].queryset = Org.objects.filter(is_vendor=True)
        return form


"""
Register Admin Pages
"""
admin.site.register(DeviceScript, DeviceScriptAdmin)
