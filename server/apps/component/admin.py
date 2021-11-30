from django.contrib import admin

from .models import *


class ComponentAdmin(admin.ModelAdmin):
    list_display = ('slug', 'external_sku', 'hw_tag', 'version', 'type', 'active', )
    exclude = ['created_by', 'images', 'slug',]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

    def get_form(self, request, obj=None, **kwargs):
        form = super(ComponentAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['org'].queryset = Org.objects.filter(is_vendor=True)
        return form

"""
Register Admin Pages
"""
admin.site.register(Component, ComponentAdmin)
