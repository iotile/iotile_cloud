import logging

from django.conf import settings

from ..base import ReportGenerator

logger = logging.getLogger(__name__)


class AnalyticsReportGenerator(ReportGenerator):

    def __init__(self, msgs, rpt, start, end, sources=None):
        super(AnalyticsReportGenerator, self).__init__(msgs, rpt, start, end, sources)

    def add_streams_for_qs(self, qs):
        for stream in qs:
            logger.info('No action: {}'.format(stream))

    def process_config(self):
        # No configuration available yet
        pass

    def generate_user_report(self):
        """
        Generate an End of Trip Summary Report

        :return: Nothing
        """

        for source_slug in self._sources:

            logger.info('Processing {}'.format(source_slug))

