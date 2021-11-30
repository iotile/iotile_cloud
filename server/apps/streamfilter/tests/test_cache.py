from django.core.cache import cache
from django.test import TestCase

from apps.physicaldevice.models import Device
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.models import StreamData
from apps.utils.test_util import TestMixin

from ..cache_utils import *
from ..cache_utils import _get_current_state_cache_key, _get_filter_cache_key
from ..models import *
from ..serializers import *


class StreamFilterCacheTestCase(TestMixin, TestCase):
    """
    Fixure includes:
    """

    def setUp(self):
        self.usersTestSetup()
        self.orgTestSetup()
        self.deviceTemplateTestSetup()
        self.v1 = StreamVariable.objects.create_variable(
            name='Var A', project=self.p1, created_by=self.u2, lid=1,
        )
        self.pd1 = Device.objects.create_device(project=self.p1, label='d1', template=self.dt1, created_by=self.u2)
        self.s1 = StreamId.objects.create_stream(
            project=self.p1, variable=self.v1, device=self.pd1, created_by=self.u2
        )

        if cache:
            cache.clear()

    def tearDown(self):
        StreamFilterAction.objects.all().delete()
        StreamFilterTrigger.objects.all().delete()
        StateTransition.objects.all().delete()
        StreamFilter.objects.all().delete()
        State.objects.all().defer()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        StreamData.objects.all().delete()
        Device.objects.all().delete()
        self.deviceTemplateTestTearDown()
        self.orgTestTearDown()
        self.userTestTearDown()

        if cache:
            cache.clear()

    def testKeys(self):
        key = _get_current_state_cache_key('s--0000-0001--0000-0000-0000-0001--1111')
        self.assertEqual(key, 'current-state:s--0000-0001--0000-0000-0000-0001--1111')
        key = _get_filter_cache_key('f--0000-0001----1111')
        self.assertEqual(key, 'filter:f--0000-0001----1111')

    def testNoCurrentState(self):
        value = get_current_cached_filter_state_for_slug('s--0000-0001--0000-0000-0000-0001--1111')
        self.assertIsNone(value)

    def testCurrentState(self):
        set_current_cached_filter_state_for_slug('s--0000-0001--0000-0000-0000-0001--1111', 'state1')
        value = get_current_cached_filter_state_for_slug('s--0000-0001--0000-0000-0000-0001--1111')
        self.assertEqual(value, 'state1')

    def testNoFilter(self):
        cached_value = cached_serialized_filter_for_gsid(self.s1.slug)
        self.assertEqual(cached_value, {'empty': True})

    def testFilterCacheForStream(self):
        f = StreamFilter.objects.create_filter_from_streamid(
            name='Filter 1', input_stream=self.s1, created_by=self.u2
        )
        ser = StreamFilterSerializer(f)
        cached_value = cached_serialized_filter_for_slug(self.s1.slug)
        self.assertEqual(cached_value, ser.data)

    def testFilterCacheForProject(self):
        f = StreamFilter.objects.create_filter_from_project_and_variable(
            name='Filter 1', proj=self.s1.project, var=self.s1.variable, created_by=self.u2
        )
        ser = StreamFilterSerializer(f)
        cached_value = cached_serialized_filter_for_slug(self.s1.slug)
        self.assertEqual(cached_value, ser.data)

    def testCachePattern(self):
        patterns = get_current_state_cache_pattern('f--0000-0001----5001')
        self.assertEqual(patterns, 'current-state:s--0000-0001--*--5001')
        patterns = get_current_state_cache_pattern('f--0000-0001--0000-0000-0000-1234--5001')
        self.assertEqual(patterns, 'current-state:s--0000-0001--0000-0000-0000-1234--5001')
