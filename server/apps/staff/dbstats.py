import datetime
import logging

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.org.models import Org
from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.stream.models import StreamId
from apps.streamer.models import StreamerReport
from apps.streamnote.models import StreamNote
from apps.utils.data_helpers.manager import DataManager

logger = logging.getLogger(__name__)


class DbStats(object):
    _labels = {
        'Users': {
            'qs': get_user_model().objects.filter(is_active=True),
            'creation_field': 'created_at'
        },
        'Orgs': {
            'qs': Org.objects.all()
        },
        'Projects': {
            'qs': Project.objects.all()
        },
        'ActiveDevices': {
            'qs': Device.objects.filter(active=True)
        },
        'ClaimedDevices': {
            'qs': Device.objects.filter(active=True, project__isnull=False),
            'creation_field': 'claimed_on'
        },
        'EnabledStreams': {
            'qs': StreamId.objects.filter(enabled=True)
        },
        'StreamData*': {
            'qs': DataManager.all_qs('data'),
            'creation_field': 'timestamp'
        },
        'StreamEvents*': {
            'qs': DataManager.all_qs('event'),
            'creation_field': 'timestamp'
        },
        'StreamNotes': {
            'qs': StreamNote.objects.all()
        },
        'StreamerReports': {
            'qs': StreamerReport.objects.all()
        }
    }
    stats = {}
    start = None
    end = None

    def __init__(self):
        stats = {}
        start = None
        end = None

    def compute_stats(self):

        for key in self._labels.keys():
            qs = self._labels[key]['qs']
            self.stats[key] = qs.count()

    def day_stats(self, days=1):
        self.end = timezone.now()
        self.start = self.end - datetime.timedelta(days=days)

        for key in self._labels.keys():
            qs = self._labels[key]['qs']

            filter_kwargs = {}
            if 'creation_field' in self._labels[key]:
                name = '{0}__gte'.format(self._labels[key]['creation_field'])
                filter_kwargs[name] = self.start
            else:
                filter_kwargs['created_on__gte'] = self.start

            try:
                self.stats[key] = qs.filter(**filter_kwargs).count()
            except Exception as e:
                logger.warning('{0} Err={1}'.format(key, e))
