from django.contrib import admin

from .models import *


class DeviceAdmin(admin.ModelAdmin):
    list_display = ('slug', 'family', 'external_sku', 'internal_sku', 'version', 'active', 'os_tag_and_version',)
    exclude = ['created_by', 'slug', 'components', 'images', ]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

    def get_form(self, request, obj=None, **kwargs):
        form = super(DeviceAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['org'].queryset = Org.objects.filter(is_vendor=True)
        return form


class DeviceSlotAdmin(admin.ModelAdmin):
    list_display = ('id', 'template', 'component', 'number', )


"""
Register Admin Pages
"""
admin.site.register(DeviceTemplate, DeviceAdmin)
admin.site.register(DeviceSlot, DeviceSlotAdmin)
