from django.contrib import admin

from .models import *


class StreamFilterAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug', 'project', )
    exclude = ['created_by', 'slug']
    readonly_fields = ('created_by', 'slug',)

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        if not obj.project:
            if obj.input_stream:
                obj.project = obj.input_stream.project
            elif obj.device:
                obj.project = obj.device.project

        obj.save()

class StreamFilterTriggerAdmin(admin.ModelAdmin):
    list_display = ('id', 'filter', 'operator', 'threshold', )
    exclude = ['created_by', ]
    readonly_fields = ('created_by', )

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

class StreamFilterActionAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'on', 'state' )
    exclude = ['created_by', ]
    readonly_fields = ('created_by', )

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

class StateAdmin(admin.ModelAdmin):
    list_display = ('label', 'slug', 'filter' )
    exclude = ['created_by', ]
    readonly_fields = ('created_by', )

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

class StateTransitionAdmin(admin.ModelAdmin):
    list_display = ('id', 'src', 'dst', 'filter')
    exclude = ['created_by', ]
    readonly_fields = ('created_by', )

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        obj.save()

"""
Register Admin Pages
"""
admin.site.register(StreamFilter, StreamFilterAdmin)
admin.site.register(StreamFilterTrigger, StreamFilterTriggerAdmin)
admin.site.register(StreamFilterAction, StreamFilterActionAdmin)
admin.site.register(State, StateAdmin)
admin.site.register(StateTransition, StateTransitionAdmin)


