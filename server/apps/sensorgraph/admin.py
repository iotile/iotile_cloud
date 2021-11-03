from django.contrib import admin

from .models import *


class SensorGraphAdmin(admin.ModelAdmin):
    list_display = ('slug', 'version', 'active', 'project_template', 'app_tag_and_version',)
    exclude = ['created_by', 'slug', ]
    readonly_fields = ['id', 'slug', 'created_by', 'created_on', 'org_properties']
    search_fields = ['name', 'slug']

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

    def get_form(self, request, obj=None, **kwargs):
        form = super(SensorGraphAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['org'].queryset = Org.objects.filter(is_vendor=True)
        return form

    def get_queryset(self, request):
        qs = super(SensorGraphAdmin, self).get_queryset(request)
        return qs.order_by('name')


class VariableTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'sg', 'label', 'lid_hex', 'derived_lid_hex', 'var_type', )
    exclude = ['created_by', ]
    readonly_fields = ['id', 'created_by', 'created_on']
    search_fields = ['label', 'lid_hex', 'sg__slug']

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

    def get_queryset(self, request):
        qs = super(VariableTemplateAdmin, self).get_queryset(request)
        return qs.order_by('sg', 'lid_hex')


class DisplayWidgetTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'sg', 'label', 'lid_hex', 'var_type', 'derived_unit_type', 'show_in_app', 'show_in_web')
    exclude = ['created_by', ]
    readonly_fields = ['id', 'created_by', 'created_on']
    search_fields = ['label', 'lid_hex', 'sg__slug']

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

    def get_queryset(self, request):
        qs = super(DisplayWidgetTemplateAdmin, self).get_queryset(request)
        return qs.order_by('sg', 'lid_hex', 'derived_unit_type')


"""
Register Admin Pages
"""
admin.site.register(SensorGraph, SensorGraphAdmin)
admin.site.register(VariableTemplate, VariableTemplateAdmin)
admin.site.register(DisplayWidgetTemplate, DisplayWidgetTemplateAdmin)
