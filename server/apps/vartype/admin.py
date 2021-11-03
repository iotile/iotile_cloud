from django.contrib import admin
from .models import VarType, VarTypeInputUnit, VarTypeOutputUnit, VarTypeDecoder, VarTypeSchema


class VarTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug', 'stream_data_type')
    exclude = ['created_by', 'slug']
    readonly_fields = ('created_by', 'slug')
    search_fields = ['slug', 'name', ]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

    def get_queryset(self, request):
        qs = super(VarTypeAdmin, self).get_queryset(request)
        return qs.order_by('name')


class VarTypeDecoderAdmin(admin.ModelAdmin):
    list_display = ('id', 'var_type', 'raw_packet_format',)
    exclude = ['created_by', ]
    readonly_fields = ('created_by', )

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


class VarTypeSchemaAdmin(admin.ModelAdmin):
    list_display = ('id', 'var_type',)
    exclude = ['created_by', ]
    readonly_fields = ('created_by', )

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


class VarTypeInputUnitAdmin(admin.ModelAdmin):
    list_display = ('id', 'var_type', 'unit_full', 'slug',)
    exclude = ['created_by', 'slug']
    readonly_fields = ('created_by', 'slug')
    search_fields = ['slug', 'var_type__slug', 'unit_full', ]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

    def get_queryset(self, request):
        qs = super(VarTypeInputUnitAdmin, self).get_queryset(request)
        return qs.order_by('unit_full')


class VarTypeOutputUnitAdmin(admin.ModelAdmin):
    list_display = ('id', 'var_type', 'unit_full', 'slug',)
    exclude = ['created_by', 'slug']
    readonly_fields = ('created_by', 'slug')
    search_fields = ['slug', 'var_type__slug', 'unit_full', ]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

    def get_queryset(self, request):
        qs = super(VarTypeOutputUnitAdmin, self).get_queryset(request)
        return qs.order_by('unit_full')


"""
Register Admin Pages
"""
admin.site.register(VarType, VarTypeAdmin)
admin.site.register(VarTypeDecoder, VarTypeDecoderAdmin)
admin.site.register(VarTypeSchema, VarTypeSchemaAdmin)
admin.site.register(VarTypeInputUnit, VarTypeInputUnitAdmin)
admin.site.register(VarTypeOutputUnit, VarTypeOutputUnitAdmin)
