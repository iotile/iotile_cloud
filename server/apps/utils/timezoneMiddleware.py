__author__ = 'dkarchmer'

import pytz

from django.utils import timezone


class TimezoneMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        tzname = request.session.get('django_timezone')

        if not tzname:
            # Get it from the Account. Should hopefully happens once per session
            user = request.user
            if user and not user.is_anonymous:
                tzname = user.time_zone
                if tzname:
                    request.session['django_timezone'] = tzname

        if tzname:
            timezone.activate(pytz.timezone(tzname))
        else:
            timezone.deactivate()

        response = self.get_response(request)

        return response
