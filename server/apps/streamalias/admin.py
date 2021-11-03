from django.contrib import admin

from .models import *


class StreamAliasAdmin(admin.ModelAdmin):
    list_display = ('id', 'slug', 'name', 'org',)
    exclude = ['created_by',]
    readonly_fields = ('formatted_gid', 'slug',)
    search_fields = ['slug', 'name', 'org',]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


class StreamAliasTapAdmin(admin.ModelAdmin):
    list_display = ('id', 'alias', 'timestamp', 'stream',)
    exclude = ['created_by',]
    search_fields = ['alias', 'stream',]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


"""
Register Admin Pages
"""
admin.site.register(StreamAlias, StreamAliasAdmin)
admin.site.register(StreamAliasTap, StreamAliasTapAdmin)
