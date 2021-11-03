from django.contrib import admin
from django import forms

from .models import *


class StreamTimeSeriesValueAdmin(admin.ModelAdmin):
    list_display = ('id', 'stream_slug', 'timestamp', 'device_seqid', 'type', 'raw_value', 'value', )
    readonly_fields = ('project_id', 'device_id', 'variable_id', 'block_id', )
    search_fields = ['stream_slug', 'project_id', 'device_id', 'variable_id', 'block_id', 'device_seqid', ]

    def queryset(self, request):
        qs = super(StreamTimeSeriesValueAdmin, self).queryset(request)
        return qs.order_by('-id')[:2]


class StreamTimeSeriesEventAdminForm(forms.ModelForm):
    def clean_extra_data(self):
        if not isinstance(self.cleaned_data["extra_data"], dict):
            raise forms.ValidationError('extra_data must be a valid dictionary object')
        return self.cleaned_data["extra_data"]


class StreamTimeSeriesEventAdmin(admin.ModelAdmin):
    form = StreamTimeSeriesEventAdminForm
    list_display = ('id', 'stream_slug', 'timestamp', 'device_seqid', 'ext', 's3_key_path', )
    readonly_fields = ('uuid', 'project_id', 'device_id', 'variable_id', 'block_id', 's3_key_path', )
    search_fields = ['stream_slug', 'uuid', 'project_id', 'device_id', 'variable_id', 'block_id', 'device_seqid', ]

    def queryset(self, request):
        qs = super(StreamTimeSeriesEventAdmin, self).queryset(request)
        return qs.order_by('-id')[:2]


"""
Register Admin Pages
"""
# admin.site.register(StreamTimeSeriesValue, StreamTimeSeriesValueAdmin)
# admin.site.register(StreamTimeSeriesEvent, StreamTimeSeriesEventAdmin)
