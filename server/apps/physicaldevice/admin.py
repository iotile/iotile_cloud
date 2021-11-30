from django.contrib import admin

from .models import *


class DeviceAdmin(admin.ModelAdmin):
    list_display = ('id', 'slug', 'project', 'template', 'sg', 'state', )
    exclude = ['created_by', 'org', 'active']
    readonly_fields = ('formatted_gid', 'slug', 'created_by', 'created_on', 'active', 'busy')
    search_fields = ['slug', 'template__slug', 'sg__slug', 'external_id']

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        if obj.project:
            obj.org = obj.project.org
        else:
            obj.org = None
        obj.set_active_from_state()
        obj.save()

    def get_form(self, request, obj=None, **kwargs):
        form = super(DeviceAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['project'].queryset = Project.objects.all().order_by('org__name', 'name')
        form.base_fields['sg'].queryset = SensorGraph.objects.all().order_by('name')
        form.base_fields['template'].queryset = DeviceTemplate.objects.all().order_by('external_sku')
        return form


class DeviceStatusAdmin(admin.ModelAdmin):
    list_display = ('device', 'last_known_id', 'last_report_ts', 'alert', 'health_check_enabled')
    readonly_fields = ('alert', )
    search_fields = ['device__slug', ]
    raw_id_fields = ('device', )



"""
Register Admin Pages
"""
admin.site.register(Device, DeviceAdmin)
admin.site.register(DeviceStatus, DeviceStatusAdmin)
