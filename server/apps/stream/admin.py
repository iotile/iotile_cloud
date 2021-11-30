from django.contrib import admin

from apps.utils.gid.convert import formatted_gsid

from .models import *


class StreamVariableAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'project', 'slug', 'var_type',)
    exclude = ['created_by', 'org',]
    readonly_fields = ('formatted_lid', 'formatted_gid', 'slug',)
    search_fields = ['slug', 'name', 'var_type__slug']

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        if obj.project:
            obj.org = obj.project.org
        obj.save()
        StreamId.objects.create_after_new_variable(var=obj)


class StreamSystemVariableAdmin(admin.ModelAdmin):
    list_display = ('id', 'variable', 'project')

    def get_form(self, request, obj=None, **kwargs):
        form = super(StreamSystemVariableAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['variable'].queryset = StreamVariable.objects.filter(project__isnull=True)
        return form


class StreamIdAdmin(admin.ModelAdmin):
    list_display = ('id', 'slug', 'enabled', 'data_type', 'data_label')
    exclude = ['created_by', 'org', ]
    readonly_fields = ('slug',)
    search_fields = ['slug', 'data_label']
    raw_id_fields = ('project', 'block', 'device', 'variable', 'derived_stream',
                     'var_type', 'input_unit', 'output_unit')

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        if obj.project:
            obj.org = obj.project.org
        if obj.project and obj.device and obj.variable:
            obj.slug = formatted_gsid(pid=obj.project.formatted_gid,
                                      did=obj.device.formatted_gid,
                                      vid=obj.variable.formatted_lid)

        obj.save()


class DisplayWidgetInstanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'widget', 'stream', 'variable', 'output_unit', 'derived_unit_selection')
    exclude = ['created_by',]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

    def get_queryset(self, request):
        qs = super(DisplayWidgetInstanceAdmin, self).get_queryset(request)
        return qs.order_by('widget')


"""
Register Admin Pages
"""
admin.site.register(StreamVariable, StreamVariableAdmin)
admin.site.register(StreamSystemVariable, StreamSystemVariableAdmin)
admin.site.register(StreamId, StreamIdAdmin)
admin.site.register(DisplayWidgetInstance, DisplayWidgetInstanceAdmin)
