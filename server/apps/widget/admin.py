from django.contrib import admin
from .models import *

class PageTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'label', 'type', 'template_path', 'created_by', )
    exclude = ['created_by', 'slug',]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


class WidgetTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'label', 'data_type', 'template_path', 'created_by', )
    exclude = ['created_by',]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


class WidgetInstanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'label', 'widget_definition', 'page_definition', 'primary_variable_id_in_hex')
    readonly_fields = ('primary_variable_id_in_hex',)
    exclude = ['created_by',]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


"""
Register Admin Pages
"""
admin.site.register(PageTemplate, PageTemplateAdmin)
admin.site.register(WidgetTemplate, WidgetTemplateAdmin)
admin.site.register(WidgetInstance, WidgetInstanceAdmin)
