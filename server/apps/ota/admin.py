from django.contrib import admin

from .models import *


class DeploymentRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'script', 'released_on', 'completed_on' )
    exclude = ['created_by',  ]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

    def get_form(self, request, obj=None, **kwargs):
        form = super(DeploymentRequestAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['org'].queryset = Org.objects.filter(is_vendor=True)
        return form


class DeploymentActionAdmin(admin.ModelAdmin):
    list_display = ('id', 'deployment', 'device', 'attempt_successful', 'device_confirmation', )


class DeviceVersionAttributeAdmin(admin.ModelAdmin):
    list_display = ('id', 'device', 'type', 'tag', 'version', 'updated_ts' )


"""
Register Admin Pages
"""
admin.site.register(DeviceVersionAttribute, DeviceVersionAttributeAdmin)
admin.site.register(DeploymentRequest, DeploymentRequestAdmin)
admin.site.register(DeploymentAction, DeploymentActionAdmin)
