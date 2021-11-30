from django import forms
from django.contrib import admin

from .models import StreamEventData


class StreamEventDataAdminForm(forms.ModelForm):
    def clean_extra_data(self):
        if not isinstance(self.cleaned_data["extra_data"], dict):
            raise forms.ValidationError('extra_data must be a valid dictionary object')
        return self.cleaned_data["extra_data"]

class StreamEventDataAdmin(admin.ModelAdmin):
    form = StreamEventDataAdminForm
    list_display = ('id', 'stream_slug', 'timestamp', 'streamer_local_id', 'ext', 's3key')
    readonly_fields = ('uuid', 'project_slug', 'device_slug', 'variable_slug', 's3key')
    search_fields = ['stream_slug', 'uuid', 'project_slug', 'device_slug', 'variable_slug', 'streamer_local_id', ]

    def get_queryset(self, request):
        qs = super(StreamEventDataAdmin, self).get_queryset(request)
        return qs.order_by('-id')

"""
Register Admin Pages
"""
admin.site.register(StreamEventData, StreamEventDataAdmin)
