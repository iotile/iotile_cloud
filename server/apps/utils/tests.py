from unittest import TestCase

from .timezone_utils import nb_seconds_since_2000, parse_datetime


class TimezoneUtilsTestCase(TestCase):
    def testSecondsSince2000(self):
        utc_dt = parse_datetime('2000-01-01T00:01:40Z')  # 100s after 2000 in UTC
        pst_dt = parse_datetime('1999-12-31T23:00:00-08:00')  # 7h after 2000 in UTC
        n1 = nb_seconds_since_2000(utc_dt)
        n2 = nb_seconds_since_2000(pst_dt)
        self.assertEqual(n1, 100)
        self.assertEqual(n2, 7 * 3600)
