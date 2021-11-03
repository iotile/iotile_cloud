from django.contrib import admin
from .models import *

class S3ImageAdmin(admin.ModelAdmin):
    raw_id_fields = ('created_by',)
    list_display = ('id', 'bucket', 'key', 'created_on', )
    fields = ( 'bucket', 'key', 'ext', 'created_by', 'thumbnail_image_tag', )
    readonly_fields = ('thumbnail_image_tag',)

"""
Register Admin Pages
"""
admin.site.register(S3Image, S3ImageAdmin)