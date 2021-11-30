from django.contrib import admin

from .forms import InvitationAdminCreateForm, InvitationAdminEditForm
from .models import Invitation


class InvitationAdmin(admin.ModelAdmin):
    list_display = ('email', 'sent_by', 'org', 'accepted')
    search_fields = ['email', ]

    def get_form(self, request, obj=None, **kwargs):
        if obj:
            kwargs['form'] = InvitationAdminEditForm
        else:
            kwargs['form'] = InvitationAdminCreateForm
            kwargs['form'].request = request
        return super(InvitationAdmin, self).get_form(request, obj, **kwargs)

    def save_model(self, request, obj, form, change):
        obj.sent_by = request.user
        obj.save()

admin.site.register(Invitation, InvitationAdmin)
