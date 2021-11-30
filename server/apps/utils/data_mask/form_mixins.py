import logging

import pytz

from django import forms

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Layout, Submit

from apps.utils.aws.redshift import get_ts_from_redshift
from apps.utils.data_helpers.manager import DataManager
from apps.utils.timezone_utils import str_to_dt_utc, str_utc

from .mask_utils import get_data_mask_date_range

DATETIME_WIDGET_OPTIONS = {
    'format': 'dd/mm/yyyy HH:ii:ss',
    'autoclose': True
}

logger = logging.getLogger(__name__)


class DataMaskFormMixin(object):

    def setup_crispy_helper(self, obj):
        assert obj
        helper = FormHelper()
        helper.form_method = 'post'

        stream_qs = self.get_streams_to_mask(obj)
        stream_slugs = [s.slug for s in stream_qs]

        note = """
            <div class="alert alert-warning alert-dismissible fade in" role="alert">
            This operation will hide data for device '{slug}'.<br>
            </div>
        """.format(slug=obj.slug)

        table = """
            <table class="table table-striped table-bordered">
            <head>
            <tr>
              <th>Variable</th>
              <th>Data Count</th>
              <th>Event Count</th>
              <th>Oldest</th>
              <th>Newest</th>
            </tr>
            </head>
            """

        alert = """
            <div class="alert alert-warning alert-dismissible fade in" role="alert">
            Select the start and end dates in UTC for all the data you would <b>like to keep</b> for this device.<br>
            Data outside of the selected time range will be <b>masked away (but NOT permanently deleted).</b>
            </div>
            """

        data_count = event_count = 0
        for stream_slug in stream_slugs:
            ts0 = ts1 = None
            stream_data_qs = DataManager.filter_qs('data', stream_slug=stream_slug)
            stream_event_qs = DataManager.filter_qs('event', stream_slug=stream_slug)
            data0 = get_ts_from_redshift(stream_data_qs.first().timestamp) if stream_data_qs.count() else None
            data1 = get_ts_from_redshift(stream_data_qs.last().timestamp) if stream_data_qs.count() else None
            event0 = stream_event_qs.first().timestamp if stream_event_qs.count() else None
            event1 = stream_event_qs.last().timestamp if stream_event_qs.count() else None
            if data0 and event0:
                ts0 = data0 if data0 > event0 else event0
            else:
                if data0:
                    ts0 = data0
                else:
                    ts0 = event0
            if data1 and event1:
                ts1 = data1 if data1 > event1 else event1
            else:
                if data1:
                    ts1 = data1
                else:
                    ts1 = event1
            table += """
                <tr>
                  <th>{stream}</th>
                  <td>{data}</td>
                  <td>{event}</td>
                  <td>{first}</td>
                  <td>{last}</td>
                </tr>
                """.format(
                stream=stream_slug.split('--')[-1],
                data=stream_data_qs.count(),
                event=stream_event_qs.count(),
                first=str_utc(ts0) if ts0 else '',
                last=str_utc(ts1) if ts1 else ''
            )
            data_count += stream_data_qs.count()
            event_count += stream_event_qs.count()

        table += """
            <tr>
              <th>Totals</th>
              <td>{data}</td>
              <td>{event}</td>
            </tr>
            """.format(
            data=data_count,
            event=event_count
        )

        table += '</table>'

        helper.layout = Layout(
            HTML(note),
            HTML('<br>'),
            HTML(table),
            HTML('<br>'),
            HTML(alert),
            HTML('<br>'),
            Div(
                Div('start', css_class='col-sm-6 col-xs-12'),
                Div('end', css_class='col-sm-6 col-xs-12'),
                css_class='row'
            ),
            HTML('<br>'),
        )
        helper.add_input(Submit('submit', 'Hide Device Data outside range', css_class='btn btn-block btn-danger submit'))

        return helper

    def clean(self):
        if self.cleaned_data.get('start') and self.cleaned_data.get('end') and self.cleaned_data.get('start') > self.cleaned_data.get('end'):
            raise forms.ValidationError("The start date must be before the end date")
        return self.cleaned_data

    """
    def clean_events(self):
        events = self.cleaned_data.get('events')
        if events:
            return [int(i) for i in events.split(',')]
        return []

    def clean_data(self):
        data = self.cleaned_data.get('data')
        if data:
            return [int(i) for i in data.split(',')]
        return []
    """

    def clean_start(self):
        """Force the value returned by the datetime widget to be a UTC (as I cannot figure out how to make the widget be UTC)"""
        start = self.cleaned_data.get('start')
        if start:
            utc_dt = start.replace(tzinfo=pytz.utc)
            logger.info('Cleaned Start timestamp: {}'.format(utc_dt))
            return utc_dt.replace(second=0, microsecond=0)
        return None

    def clean_end(self):
        """Force the value returned by the datetime widget to be a UTC (as I cannot figure out how to make the widget be UTC)"""
        end = self.cleaned_data.get('end')
        if end:
            utc_dt = end.replace(tzinfo=pytz.utc)
            logger.info('Cleaned End timestamp: {}'.format(utc_dt))
            return utc_dt.replace(second=0, microsecond=0)
        return None
