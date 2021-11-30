import os
import struct

from django.test import TestCase

from ..models import *
from ..serializers import *
from .parser import READINGS_FORMAT, ReportParser


class StreamerReportParsingTestCase(TestCase):

    def _full_path(self, filename):
        module_path = os.path.dirname(os.path.dirname(__file__))
        return os.path.join(module_path, 'data', 'reports', filename)

    def testUnpackReading(self):
        raw = struct.pack('<HHLLL', 0x5001, 0x1, 0x100, 0x10, 25)
        rp = ReportParser()
        point = rp._unpack(READINGS_FORMAT, raw)
        self.assertEqual(point['id'], 0x100)
        self.assertEqual(point['stream'], 0x5001)
        self.assertEqual(point['timestamp'], 0x10)
        self.assertEqual(point['value'], 25)

    def testUnpackNegative(self):
        raw = struct.pack('<HHLLl', 0x5001, 0x1, 0x100, 0x10, -25)
        rp = ReportParser()
        point = rp._unpack(READINGS_FORMAT, raw)
        self.assertEqual(point['id'], 0x100)
        self.assertEqual(point['stream'], 0x5001)
        self.assertEqual(point['timestamp'], 0x10)
        # Testing how we could convert unsigned to signed
        raw_value = struct.pack('<L', point['value'])
        (value,) = struct.unpack('<l', raw_value)
        self.assertEqual(value, -25)

    def testValidFooter(self):
        test_filename = self._full_path('valid_16_readings.bin')

        with open(test_filename, 'rb') as fp:
            rp = ReportParser()
            rp.parse_header(fp)
            self.assertEqual(rp.header['fmt'], 1)
            self.assertEqual(rp.header['len_low'], 44)
            self.assertEqual(rp.header['len_high'], 1)
            rp.parse_footer(fp)
            self.assertEqual(rp.footer['lowest_id'], 1)
            self.assertEqual(rp.footer['highest_id'], 16)
            self.assertTrue(rp.check_report_hash(fp))

            rp.parse_readings(fp)
            self.assertEqual(len(rp.data), 16)
            self.assertEqual(rp.data[0]['id'], 1)
            self.assertEqual(rp.data[15]['id'], 16)
            self.assertEqual(rp.data[0]['value'], 0)
            self.assertEqual(rp.data[15]['value'], 15)
            self.assertEqual(rp.data[0]['timestamp'], 0)
            self.assertEqual(rp.data[15]['timestamp'], 15)
            self.assertEqual(rp.length, 300)

    def testInvalidFooter(self):
        test_filename = self._full_path('invalid_footer_16_readings.bin')

        with open(test_filename, 'rb') as fp:
            rp = ReportParser()
            rp.parse_header(fp)
            self.assertEqual(rp.header['fmt'], 1)
            rp.parse_footer(fp)
            self.assertEqual(rp.footer['lowest_id'], 1)
            self.assertEqual(rp.footer['highest_id'], 16)
            self.assertFalse(rp.check_report_hash(fp))

    def testFooterLengthTooLong(self):
        test_filename = self._full_path('length_too_long_16_readings.bin')

        with open(test_filename, 'rb') as fp:
            rp = ReportParser()
            rp.parse_header(fp)
            self.assertEqual(rp.header['fmt'], 1)
            rp.parse_footer(fp)
            self.assertEqual(rp.footer['lowest_id'], 1)
            self.assertEqual(rp.footer['highest_id'], 16)
            self.assertFalse(rp.check_report_hash(fp))

    def testFooterLengthTooShort(self):
        test_filename = self._full_path('length_too_short_16_readings.bin')

        with open(test_filename, 'rb') as fp:
            rp = ReportParser()
            rp.parse_header(fp)
            self.assertEqual(rp.header['fmt'], 1)
            rp.parse_footer(fp)
            self.assertEqual(rp.footer['lowest_id'], 1)
            self.assertEqual(rp.footer['highest_id'], 16)
            self.assertFalse(rp.check_report_hash(fp))

    def testChoppedReport(self):
        test_filename = self._full_path('chopped.bin')

        with open(test_filename, 'rb') as fp:
            rp = ReportParser()
            rp.parse_header(fp)
            self.assertEqual(rp.header['fmt'], 1)
            rp.parse_footer(fp)
            self.assertEqual(rp.footer['lowest_id'], 81)
            self.assertEqual(rp.footer['highest_id'], 14382)
            self.assertTrue(rp.chopped_off())



