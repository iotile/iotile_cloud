import json
from django.contrib import admin
from django.forms import TextInput, Textarea
from django.contrib.postgres.forms import SimpleArrayField
from django.contrib.postgres.fields import ArrayField

from .models import *
from .forms import UserReportAdminForm


class UserReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'org', 'label', 'generator')
    exclude = ['created_by',]
    readonly_fields = ('created_by', 'created_on', )
    search_fields = ['label', ]
    form = UserReportAdminForm

    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={'size': '80'})},
        ArrayField: {'widget': TextInput(attrs={'size': '80'})},
    }

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


class GeneratedUserReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'org', 'label', 'source_ref', 'status')
    exclude = ['created_by',]
    readonly_fields = ('created_by', 'created_on', )
    search_fields = ['source_ref', ]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


"""
Register Admin Pages
"""
admin.site.register(UserReport, UserReportAdmin)
admin.site.register(GeneratedUserReport, GeneratedUserReportAdmin)
