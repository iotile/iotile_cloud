from django.contrib import admin

from .models import *


class StreamerAdmin(admin.ModelAdmin):
    list_display = ('id', 'slug', 'last_id',  'selector',)
    exclude = ['created_by', ]
    readonly_fields = ('slug',)
    raw_id_fields = ['device',]
    search_fields = ['slug', 'selector']


    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


class StreamerReportAdmin(admin.ModelAdmin):
    raw_id_fields = ('streamer', )
    list_display = ('id', 'streamer', 'actual_first_id', 'actual_last_id', 'created_on', )
    exclude = ['created_by', ]
    search_fields = ['id', 'streamer__slug', ]


    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


"""
Register Admin Pages
"""
admin.site.register(Streamer, StreamerAdmin)
admin.site.register(StreamerReport, StreamerReportAdmin)

