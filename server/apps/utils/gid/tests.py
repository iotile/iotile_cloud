from django.test import TestCase

from .convert import *

class GIDTests(TestCase):

    def testBasicInt2Gid(self):
        self.assertEqual(int16gid(15), '000f')
        self.assertEqual(int16gid(1030), '0406')
        self.assertEqual(int16gid(40960), 'a000')
        self.assertEqual(int16gid(65536), '0000')
        self.assertEqual(int16gid((0xff5b<<32)+1024), '0400')

        self.assertEqual(int32gid(15), '0000-000f')
        self.assertEqual(int32gid(1030), '0000-0406')
        self.assertEqual(int32gid(40960), '0000-a000')
        self.assertEqual(int32gid(65536), '0001-0000')
        self.assertEqual(int32gid((0xff5b<<32)+1024), '0000-0400')

        self.assertEqual(int64gid(15), '0000-0000-0000-000f')
        self.assertEqual(int64gid(1030), '0000-0000-0000-0406')
        self.assertEqual(int64gid(40960), '0000-0000-0000-a000')
        self.assertEqual(int64gid(65536), '0000-0000-0001-0000')
        self.assertEqual(int64gid((0xff5b<<32)+1024), '0000-ff5b-0000-0400')

    def testFixGid(self):
        self.assertEqual(fix_gid('00ff', 3), '0000-0000-00ff')

    def testDeviceIds(self):
        self.assertEqual(formatted_gdid('00ff'), 'd--0000-0000-0000-00ff')
        self.assertEqual(formatted_gdid('0000-00ff'), 'd--0000-0000-0000-00ff')
        self.assertEqual(formatted_gdid('0000-0000-00ff'), 'd--0000-0000-0000-00ff')
        self.assertEqual(formatted_gdid('ff00-0000-0000'), 'd--0000-ff00-0000-0000')
        self.assertEqual(formatted_gdid('ff00-ff00-0000-0000'), 'd--0000-ff00-0000-0000')
        self.assertEqual(formatted_gdid('ff00-0000-0000', bid='0001'), 'd--0001-ff00-0000-0000')

    def testInt2Did(self):
        num = 15
        self.assertEqual(int2did(num), '0000-0000-0000-000f')
        self.assertEqual(int2did_short(num), '0000-0000-000f')

    def testgetDeviceBlockId(self):
        self.assertEqual(get_device_and_block_by_did('d--0000-0000-0000-0001'), (0, 1))
        self.assertEqual(get_device_and_block_by_did('d--0002-0000-0000-0001'), (2, 1))
        self.assertEqual(get_device_and_block_by_did('b--0002-0000-0000-0001'), (2, 1))
        self.assertEqual(get_device_and_block_by_did('foo'), (None, None))
