from django.contrib.sites.shortcuts import get_current_site
from django.utils.functional import SimpleLazyObject

__author__ = 'dkarchmer'

from django.conf import settings


def basics(request):
    # Used to enable  production only behavior
    context = {
        'production': settings.PRODUCTION
    }

    return context

def site(request):
    return {
        'site': SimpleLazyObject(lambda: get_current_site(request)),
    }
