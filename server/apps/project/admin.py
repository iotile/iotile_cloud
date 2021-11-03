from django.contrib import admin
from .models import *

class ProjectAdmin(admin.ModelAdmin):
    raw_id_fields = ('created_by', )
    list_display = ('id', 'slug', 'name', 'org', 'project_template')
    readonly_fields = ('formatted_gid', 'slug', 'created_by', 'created_on')
    search_fields = ['name', 'id', 'org__slug', 'project_template__slug']

    def get_queryset(self, request):
        qs = super(ProjectAdmin, self).get_queryset(request)
        return qs.order_by('slug')

    def get_form(self, request, obj=None, **kwargs):
        form = super(ProjectAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['org'].queryset = Org.objects.all().order_by('name')
        return form


"""
Register Admin Pages
"""
admin.site.register(Project, ProjectAdmin)
