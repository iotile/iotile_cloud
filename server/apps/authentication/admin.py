from django.contrib import admin

from .forms import AdminUserChangeForm, AdminUserCreationForm
from .models import *


class AccountAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'email', 'name', 'created_at', 'last_login', 'is_active', 'is_staff')
    search_fields = ['username', 'name', 'email']
    readonly_fields = ('slug', 'created_at')

    def get_form(self, request, obj=None, **kwargs):

        if obj:
            return AdminUserChangeForm
        else:
            return AdminUserCreationForm


"""
Register Admin Pages
"""
admin.site.register(Account, AccountAdmin)
