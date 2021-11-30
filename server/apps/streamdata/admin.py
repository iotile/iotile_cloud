from django.contrib import admin

from .models import StreamData


class StreamDataAdmin(admin.ModelAdmin):
    list_display = ('id', 'stream_slug', 'timestamp', 'streamer_local_id', 'type', 'int_value', 'value')
    readonly_fields = ('project_slug', 'device_slug', 'variable_slug',)
    search_fields = ['stream_slug', 'project_slug', 'device_slug', 'variable_slug', 'streamer_local_id', ]

    def get_queryset(self, request):
        qs = super(StreamDataAdmin, self).get_queryset(request)
        return qs.order_by('-id')



"""
Register Admin Pages
"""
admin.site.register(StreamData, StreamDataAdmin)
