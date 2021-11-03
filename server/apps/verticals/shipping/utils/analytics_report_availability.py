from apps.streamevent.models import StreamEventData
from apps.streamdata.models import StreamData
from apps.utils.data_mask.mask_utils import get_data_mask_date_range
from apps.utils.timezone_utils import str_to_dt_utc

from apps.verticals.helpers.analytics_report_availability_helper import AnalyticsReportAvailabilityHelpter


class ShippingAnalyticsReportAvailabilityHelpter(AnalyticsReportAvailabilityHelpter):
    """
    Shipping Application Specific code to determine if a given device or block
    can generate any analytics reports
    """

    def get_availability_payload(self):
        extra = {}

        assert self._obj and self._obj.sg

        # For now,check if we either have one shock event
        # or one environmental data point (temp)
        shock_stream_slug = self._obj.get_stream_slug_for('5020')
        shock_qs = StreamEventData.objects.filter(
            stream_slug=shock_stream_slug
        ).exclude(extra_data__has_key='error')

        temp_stream_slug = self._obj.get_stream_slug_for('5023')
        temp_qs = StreamData.objects.filter(
            stream_slug=temp_stream_slug
        )

        # (Accounting for any data mask)
        mask = get_data_mask_date_range(self._obj)
        if mask and mask['start']:
            mask_start = str_to_dt_utc(mask['start'])
            shock_qs = shock_qs.filter(timestamp__gte=mask_start)
            temp_qs = temp_qs.filter(timestamp__gte=mask_start)
        if mask and mask['end']:
            mask_end = str_to_dt_utc(mask['end'])
            shock_qs = shock_qs.filter(timestamp__lt=mask_end)
            temp_qs = temp_qs.filter(timestamp__lt=mask_end)

        have_data = shock_qs.exists() or temp_qs.exists()

        if have_data:
            code = 'AVAILABLE'
            msg = 'Analytic Reports'
            extra = {
                'reports': [
                    {
                        "key": "shipment_overview",
                        "label": "Shipping - Analytics Overview"
                    },
                    {
                        "key": "shipment_details",
                        "label": "Shipping - Analytics Details"
                    }
                ]
            }
        else:
            code = 'NOT_AVAILABLE'
            msg = 'Trip data not ready (No device data found)'

        return {
            'slug': self._obj.slug,
            'code': code,
            'msg': msg,
            'extra': extra
        }


