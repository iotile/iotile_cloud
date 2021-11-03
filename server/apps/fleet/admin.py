from django.contrib import admin
from .models import *

class FleetAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug', 'org', 'is_network')
    exclude = ['created_by', 'slug']
    readonly_fields = ('created_by', 'created_on')
    search_fields = ['name',]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

    def get_queryset(self, request):
        qs = super(FleetAdmin, self).get_queryset(request)
        return qs.order_by('slug')


class FleetMembershipAdmin(admin.ModelAdmin):
    list_display = ('id', 'device', 'fleet', 'created_on')
    raw_id_fields = ('device', )
    search_fields = ['device__slug', 'fleet__slug', 'fleet__name']

    def get_form(self, request, obj=None, **kwargs):
        form = super(FleetMembershipAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['fleet'].queryset = Fleet.objects.all().order_by('name')
        return form


"""
Register Admin Pages
"""
admin.site.register(Fleet, FleetAdmin)
admin.site.register(FleetMembership, FleetMembershipAdmin)