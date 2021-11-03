import datetime
import dateutil.parser

from apps.stream.models import StreamId
from apps.streamalias.models import StreamAlias, StreamAliasTap
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.physicaldevice.models import Device


class TestStreamAliasHelper(object):
    """
    Methods to help test Stream Aliases
    """

    def create_device_and_associated_stream(self, dev_label, dev_template=None, user=None, project=None):
        assert self.dt1
        assert self.u3
        assert self.p2
        dev_template = dev_template or self.dt1
        user = user or self.u3
        project = project or self.p2
        pd = Device.objects.create_device(project=project, label=dev_label, template=dev_template, created_by=user)
        StreamId.objects.create_after_new_device(pd)
        return StreamId.objects.get(device=pd)

    def fill_stream_with_data(self, stream, n, ts_start, ts_step):
        ts_range = (ts_start + i * datetime.timedelta(seconds=ts_step) for i in range(n))
        for i, ts in enumerate(ts_range):
            StreamData.objects.create(
                stream_slug=stream.slug,
                type='Num',
                timestamp=ts,
                int_value=i
            )

    def fill_stream_with_events(self, stream, n, ts_start, ts_step):
        ts_range = (ts_start + i * datetime.timedelta(seconds=ts_step) for i in range(n))
        for i, ts in enumerate(ts_range):
            StreamEventData.objects.create(
                stream_slug=stream.slug,
                timestamp=ts,
            )

    def create_alias(self, user, name, org, list_of_taps=[]):
        sa = StreamAlias.objects.create(
            name=name,
            org=org,
            created_by=user
        )
        for tap in list_of_taps:
            StreamAliasTap.objects.create(
                alias=sa,
                timestamp=tap['ts'],
                stream=tap['stream'],
                created_by=user
            )
        return sa

    def assert_data_from_correct_stream(self, results, slices_list):
        assert self.assertEqual
        for res in results:
            res_ts = dateutil.parser.parse(res['timestamp'])
            for slice_object in slices_list:
                if slice_object['start'] <= res_ts < slice_object['end']:
                    self.assertEqual(res['stream'], slice_object['stream'].slug)
                    break
            else:
                raise ValueError('Every result should be tested')

    def assert_results_are_ordered_by_timestamp(self, results):
        assert self.assertTrue
        def datetime_of_result(res): return dateutil.parser.parse(res['timestamp'])
        def timestamp_lte(res1, res2): return datetime_of_result(res1) <= datetime_of_result(res2)
        for i in range(len(results) - 1):
            self.assertTrue(timestamp_lte(results[i], results[i+1]))
