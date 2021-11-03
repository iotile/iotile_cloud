import logging

from django.db.models import Q

from .models import StreamAlias

logger = logging.getLogger(__name__)


class StreamAliasHelper(object):

    @staticmethod
    def get_filter_q_for_slug(alias_slug):
        """Function to build a query for an alias.

        This function builds a query from an alias. This query is meant to
        be used to filter StreamData or StreamEventData objects (to get the
        data and events corresponding to the StreamAlias).

        The query is built by using the StreamAliasTap objects of the StreamAlias.

        :param alias_slug: slug of the StreamAlias
        :return: a Q object representing the query
        """
        alias = StreamAlias.objects.get(slug=alias_slug)
        alias_taps = alias.taps.order_by('timestamp').all()
        q = Q()
        t0 = t1 = None
        # build a query from 'slices' defined by taps
        for tap in alias_taps:
            # t0 is the current tap
            # its timestamp represents the beginning of the slice
            # for this slice: data/events are taken from this tap
            if not t0:
                t0 = tap
            # t1 is the next tap
            # its timestamp represents the end of the slice
            elif not t1:
                t1 = tap
            # t0 and t1 define a slice which is used to build the query
            if t0 and t1:
                q = q | (
                    Q(timestamp__gte=t0.timestamp) &
                    Q(timestamp__lt=t1.timestamp) &
                    Q(stream_slug=t0.stream.slug)
                )
                # t1 will be the 'current tap' of the next iteration
                t0 = t1
                t1 = None
        # handle leftover: 'last slice' whose beginning is t0's timestamp and with no ending
        if t0:
            q = q | (
                Q(timestamp__gte=t0.timestamp) &
                Q(stream_slug=t0.stream.slug)
            )
            return q
        # case of an empty alias: return a query representing nothing
        return Q(pk__isnull=True)
