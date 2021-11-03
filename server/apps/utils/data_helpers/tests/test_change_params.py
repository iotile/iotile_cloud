from unittest import mock

from django.test import TestCase

from apps.utils.data_helpers.change_params import change_params


class ChangeParamsTestCase(TestCase):

    def setUp(self):
        self.some_function = mock.MagicMock(name='some_function')
    
        @change_params
        def decorated_function(**kwargs):
            return self.some_function(**kwargs)
        
        self.decorated_function = decorated_function

    def test_change_single_value(self):
        # project slug
        self.decorated_function(project_slug='p--0000-0008')
        self.some_function.assert_called_with(project_id=8)

        # device_slug and variable_slug
        self.decorated_function(device_slug='d--0000-0000-0000-0053', variable_slug='v--0000-0008--5003')
        self.some_function.assert_called_with(device_id=83, project_id=8, variable_id=20483, block_id=None)

        # streamer_local_id, dirty_ts, and int_value with lookups
        self.decorated_function(streamer_local_id__exact=4552, dirty_ts=False, int_value__gte=2000, int_value__lt=3000)
        self.some_function.assert_called_with(device_seqid__exact=4552, raw_value__gte=2000, raw_value__lt=3000)

        # inconsistent variable_slug and project_slug
        with self.assertRaises(ValueError):
            self.decorated_function(project_slug='p--0000-0007', variable_slug='v--0000-0008--5003')

    def test_change_multiple_values(self):
        # project slug
        self.decorated_function(project_slug__in=['p--0000-0008'])
        self.some_function.assert_called_with(project_id__in=[8])

        # device_slug and variable_slug
        self.decorated_function(device_slug__in=('d--0000-0000-0000-0053', 'd--0000-0000-0000-0054'), variable_slug__in=['v--0000-0008--5002', 'v--0000-0008--5003'])
        self.some_function.assert_called_with(device_id__in=(83, 84), project_id__in=[8, 8], variable_id__in=[20482, 20483], block_id__in=(None, None))

        # streamer_local_id, dirty_ts, and int_value with lookups
        self.decorated_function(streamer_local_id__exact=4552, int_value__range=(2000, 3000))
        self.some_function.assert_called_with(device_seqid__exact=4552, raw_value__range=(2000, 3000))

        # consistent variable_slug and project_slug shouldn't raise exception
        self.decorated_function(project_slug__in=('p--0000-0007', 'p--0000-0008'), variable_slug__in=('v--0000-0008--5003', 'v--0000-0009--5003'), device_slug='d--0000-0000-0000-0053')    
        self.some_function.assert_called_with(project_id__in=(8,), variable_id__in=(20483, 20483), device_id=83, block_id=None)
