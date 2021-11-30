from django.contrib import admin

from .models import *


class S3FileAdmin(admin.ModelAdmin):
    raw_id_fields = ('created_by',)
    list_display = ('id', 'key', 'title', )
    fields = ( 'title', 'bucket', 'key', 'created_by', )

"""
Register Admin Pages
"""
admin.site.register(S3File, S3FileAdmin)
