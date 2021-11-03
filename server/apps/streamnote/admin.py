from django.contrib import admin

from .models import StreamNote

class StreamNoteAdmin(admin.ModelAdmin):
    list_display = ('id', 'target_slug', 'timestamp', 'type', 'created_by')
    search_fields = ['target_slug', ]
    readonly_fields =  ['created_by', ]
    raw_id_fields = ('created_by', )

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()


"""
Register Admin Pages
"""
admin.site.register(StreamNote, StreamNoteAdmin)
