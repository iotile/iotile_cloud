
__author__ = 'dkarchmer'

from django.conf import settings

from .models import Org


def active_org(request):
    org = None

    resolver_match = request.resolver_match
    if resolver_match:
        if 'org_slug' in resolver_match.kwargs:
            org_slug = resolver_match.kwargs['org_slug']
            try:
                org = Org.objects.get(slug=org_slug)
            except Org.DoesNotExist:
                pass

    context = {
        'org': org
    }

    return context