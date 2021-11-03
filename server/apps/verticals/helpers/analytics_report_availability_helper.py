
class AnalyticsReportAvailabilityHelpter(object):
    """
    Helper class to help figure out if a given device or
    data block has any application (verticals) specific
    analytics Reports
    """
    _obj = None

    def __init__(self, device_or_block):
        self._obj = device_or_block

    def get_availability_payload(self):
        code = 'NOT_SUPPORTED'
        msg = 'Feature not supported'
        extra = {}
        slug = self._obj.slug if self._obj else 'N/A'

        return {
            'slug': slug,
            'code': code,
            'msg': msg,
            'extra': extra
        }
